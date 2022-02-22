# -*- coding: utf-8 -*-
#
# Rotina para seleção de embarcações a partir do cruzamento dos dados posicionais
# de AIS com simulações de dispersão de óleo
#
# Autor: Diego Xavier Bezerra - Bolsista projeto CNPq 06/2020
# Email: diegoxavier95@gmail.com
# Data 21/02/2022
#

# Importar módulos
from datetime import datetime as dt
from datetime import timedelta
import pandas as pd
import geopandas as gpd
import os

import rasterio
from shapely.geometry import box
import subprocess
import numpy as np
from sklearn import metrics
from glob import glob
import gdal
from descartes import PolygonPatch
from gdalconst import GA_ReadOnly
from shapely.geometry import Point, LineString, Polygon
import matplotlib.patches as pat
import zipfile
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.lines as mlines
from matplotlib import colors

# # 2022-01-16 06:58:37
# INDEX? sem index - pois pandas vai criar
# dt eh timestamp
# mmsi,nome,irin,imo,tipo,lat,lon,rumo,velocidade,fonte,timestamp

# CARREGAR SIMULAÇÃO
simul_path = r"./simul_back_100_Fortaleza_2m_ts.csv"
simul = pd.read_csv(simul_path, index_col=0)
simul = simul.dropna()

    # Criar timestamp
simul['dt'] = pd.to_datetime(simul['timestamp'], format='%Y-%m-%d %H:%M')
simul = simul.sort_values(by='dt')

    # Criar GeoDataFrame
parcels = gpd.GeoDataFrame(simul, geometry=gpd.points_from_xy(simul.lon, simul.lat))
parcels.crs = {'init': 'epsg:4326'}
parcels['dt'] = pd.to_datetime(parcels['timestamp'], format='%Y-%m-%d %H:%M')

# CARREGAR AIS
ais = pd.read_csv('./AIS_CE_202201.csv')


# MATCHUP ESPAÇO-TEMPORAL
pd.options.mode.chained_assignment = None  # default='warn'

dt_ais_series = gdf['dt']
within_lst = []
tdelta = 12  # hours
buffer_size = 0.2  # 0.2 decimal degrees ~ 22 km

for row in parcels.itertuples():
    print(row.Index, '/', parcels.shape[0])

    # Match temporal
    hour_ini, hour_final = row.dt - timedelta(hours=tdelta/2), row.dt + timedelta(hours=tdelta/2)
    hour_filtered = gdf[(dt_ais_series > hour_ini) & (dt_ais_series <= hour_final)]
    if hour_filtered.size != 0:
        # print(hour_filtered)

        # Match espacial
        polygon = row.geometry.buffer(buffer_size)
        suspects = hour_filtered[hour_filtered.geometry.within(polygon)]

        if suspects.size != 0:
            closest_time = abs(suspects.dt - row.dt)
            tdelta_h = closest_time.dt.total_seconds() / 3600
            parcel_idx = row.Index

            suspects['parcel_idx'] = parcel_idx
            suspects['tdelta_h'] = tdelta_h
            within_lst.append(suspects)
            # print(suspects)

            # break
            # break
            # break

gdf_suspects = pd.concat(within_lst).drop_duplicates().sort_values(by='dt')


# SELECIONAR MELHOR MENSAGEM AIS
