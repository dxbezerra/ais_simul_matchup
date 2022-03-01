# -*- coding: utf-8 -*-
#
# Rotina para seleção de embarcações a partir do cruzamento dos dados posicionais
# de AIS com simulações de dispersão de óleo
#
# Autor: Diego Xavier Bezerra - Bolsista projeto CNPq 06/2020
# Email: diegoxavier95@gmail.com
# Data 22/02/2022
# Versão 1.0.1

# IMPORTAR MÓDULOS
from datetime import timedelta
import pandas as pd
import geopandas as gpd
import os
from matplotlib import pyplot as plt

# IGNORAR WARNINGS
# mmsi,nome,irin,imo,tipo,lat,lon,rumo,velocidade,fonte,timestamp
# for i, row in parcels.iterrows():
#     parcels.loc[i, 'timestamp'] = f"{str(int(row.ano))}-{str(int(row.mes)).zfill(2)}-{str(int(row.dia)).zfill(2)} {str(int(row.hora)).zfill(2)}:{str(int(row['min'])).zfill(2)}:00"
#
# parcels.dropna()[['n_parcel','lat','lon','timestamp']].to_csv(r"G:\My Drive\INPE\dissertacao\edital_cnpq06\oleo_ce_2022\simul_back_100_Fortaleza_2m_v2\simul_back_100_Fortaleza_2m_v2_ts.csv", index=False)

pd.options.mode.chained_assignment = None  # default='warn'


def csv2gdf(csv_path):
    '''
    Rotina para carregar o arquivo .csv (deve estar organizado) e gerar
    o GeoDataFrame para posterior cruzamento espaço-temporal
    '''

    # Carregar arquivo csv
    csv = pd.read_csv(csv_path)

    # Criar objeto datetime para o cruzamento temporal
    csv['dt'] = pd.to_datetime(csv['timestamp'], format='%Y-%m-%d %H:%M:%S')

    # Criar GeoDataFrame para o cruzamento espacial
    csv_gdf = gpd.GeoDataFrame(csv, geometry=gpd.points_from_xy(csv.lon, csv.lat))
    csv_gdf.crs = {'init': 'epsg:4326'}  # Setar sistema de coordenadas WGS-84

    return csv_gdf


def matchup(simul, ais, tdelta=12, buffer_size=0.2):
    '''
    Rotina para matchup espaço-temporal

    simul: GeoDataFrame dos pontos resultantes da simulação de dispersão de óleo
    ais: GeoDataFrame das mensagens AIS
    tdelta: diferença do tempo (em horas) para busca temporal. 12h buscará +/- 6h
    de diferenca entre parcelas e AIS.
    buffer_size: tamanho da área de busca em volta das parcelas da simulação (graus decimais)
    0.2 graus é aproximadamente 22 km no equador.
    '''

    dt_ais_series = ais['dt']  # série temporal das mensagens ais
    within_lst = []  # lista vazia para guardar selecionados

    # Loop para cada parcela da simulação (cada linha da tabela simul)
    for row in simul.itertuples():
        print('Parcela', row.Index+1, 'de', simul.shape[0])

        # Match temporal
        hour_ini, hour_final = row.dt - timedelta(hours=tdelta/2), row.dt + timedelta(hours=tdelta/2)  # obtém hora inicial e final de acordo com tdelta setado (+/- se de tdelta for 12h)
        hour_filtered = ais[(dt_ais_series > hour_ini) & (dt_ais_series <= hour_final)]  # seleção das msgs AIS que casam temporalmente

        # Match espacial
        polygon = row.geometry.buffer(buffer_size)  # cria região de buffer (círculo envolto a parcela da simulação)
        suspects = hour_filtered[hour_filtered.geometry.within(polygon)]  # obtém mensagens AIS que estão dentro do círculo

        # Se houver registro de suspeitos, prosseguir para guardá-los na lista within_lst
        if suspects.size != 0:

            # Calcular tempo entre suspeito e parcela
            closest_time = abs(suspects.dt - row.dt)
            tdelta_h = closest_time.dt.total_seconds() / 3600

            # Obter identificação da parcela
            parcel_idx = row.Index

            # Guardar informações na lista
            suspects['parcel_idx'] = parcel_idx
            suspects['tdelta_h'] = tdelta_h
            within_lst.append(suspects)

    # Transformar lista para GeoDataFrame
    suspects_gdf = pd.concat(within_lst).drop_duplicates().sort_values(by='dt')

    return suspects_gdf


def refine(suspects_gdf):
    '''
    Algumas mensagens de mesma posição ocorrem mais que uma vez.
    Então esta função realiza refino das embarcações supeitas.
    '''

    print('Refininando resultados...')
    # Primeiro cria-se uma chave única de posição
    suspects_gdf['pos_unq'] = suspects_gdf.lat * suspects_gdf.lon

    # Para cada chave única, seleciona-se a mensagem mais próxima temporalmente
    suspects_refined_lst = [suspects_gdf.loc[suspects_gdf['pos_unq'] == unq_key].sort_values('tdelta_h').iloc[0] for unq_key in suspects_gdf.pos_unq.unique()]

    suspects_refined = gpd.GeoDataFrame(suspects_refined_lst)  # recria o GeoDataFrame

    # Contagem das embarcações
    ships_suspects = suspects_refined.MMSI.unique()
    ship_types = []
    for unq_mmsi in ships_suspects:
        slct = suspects_refined[suspects_refined.MMSI == unq_mmsi]
        ship_types.append(slct.Tipo.dropna().unique())

    ship_types = [tp[0] for tp in ship_types if tp.size > 0]

    print(f'Total de Embarcações interceptadas: {ships_suspects.size}')
    print(f'das quais {len(ship_types)} possuem identificação de Tipo')

    return suspects_refined


def write(suspects_refined, filename, save_shp=False):
    '''
    Salva GeoDataFrame em formatos shapefile (para usar em SIGs) e .csv (tabela)
    '''
    suspects_refined.to_csv(f'./{filename}.csv')

    if save_shp:
        suspects_tmp = suspects_refined.drop('dt', axis=1)
        suspects_tmp.crs = {'init': 'epsg:4326'}  # Setar sistema de coordenadas WGS-84
        suspects_tmp.to_file(f'./{filename}.shp')


def plot(simul, suspects_gdf):
    fig, ax = plt.subplots(dpi=150)

    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    world.plot(ax=ax, color='lightgray', edgecolor='black', markersize=8)

    simul.plot(ax=ax, c='r', marker='.', markersize=4)
    suspects_gdf.plot(ax=ax, c='g', marker='D', markersize=4)

    ax.set_title('Simulação vs. Embarcações suspeitas')
    ax.set_xlabel('Longitude (°)'), ax.set_ylabel('Latitude (°)')
    ax.set_xlim(-50, -10), ax.set_ylim(-30, 10)
    ax.grid(ls=':', color='dimgray', zorder=10)

    plt.show()
    plt.close()


# INPUTS
WDIR = r'C:\Users\diego_home\Documents\BLOG_PORTFOLIO\ais_simul_matchup'
os.chdir(WDIR)  # Setar diretório de trabalho

SIMUL_PATH = r"./simul_back_Fortaleza_subset.csv"
AIS_PATH = r"./AIS_CE_202201_subset.csv"
FILENAME_OUT = 'AIS_CE_202201_subset_suspects'

# 1. CARREGAR AIS E SIMULAÇAO
simul = csv2gdf(SIMUL_PATH)
ais = csv2gdf(AIS_PATH)

# 2. MATCHUP ESPAÇO-TEMPORAL
suspects_gdf = matchup(simul, ais, tdelta=12, buffer_size=0.2)

# 3. REFINAR RESULTADOS
suspects_refined = refine(suspects_gdf)

# 4. SALVAR
write(suspects_refined, FILENAME_OUT, save_shp=True)

# 5. PLOTAR SIMULAÇAO VS EMBARCAÇÕES SUSPEITAS
plot(simul, suspects_gdf)
