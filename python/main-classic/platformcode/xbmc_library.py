# -*- coding: utf-8 -*-
# ------------------------------------------------------------
# pelisalacarta 4
# Copyright 2015 tvalacarta@gmail.com
# http://blog.tvalacarta.info/plugin-xbmc/pelisalacarta/
#
# Distributed under the terms of GNU General Public License v3 (GPLv3)
# http://www.gnu.org/licenses/gpl-3.0.html
# ------------------------------------------------------------
# This file is part of pelisalacarta 4.
#
# pelisalacarta 4 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pelisalacarta 4 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pelisalacarta 4.  If not, see <http://www.gnu.org/licenses/>.
# ------------------------------------------------------------
# XBMC Library Tools
# ------------------------------------------------------------

import sys
import urllib2
import xbmc
from threading import Thread
from core import config
from core import filetools
from core import jsontools
from core import logger
from core.library import TVSHOWS_PATH, FOLDER_TVSHOWS, FOLDER_MOVIES
from platformcode import platformtools
from platformcode.xbmc_helpers import execute_sql_kodi


addon_name = sys.argv[0].strip()
if not addon_name or addon_name.startswith("default.py"):
    addon_name = "plugin://plugin.video.pelisalacarta/"


modo_cliente = config.get_setting("library_mode", "biblioteca")
# Host name where XBMC is running, leave as localhost if on this PC
# Make sure "Allow control of XBMC via HTTP" is set to ON in Settings ->
# Services -> Webserver
xbmc_host = config.get_setting("xbmc_host", "biblioteca")
# Configured in Settings -> Services -> Webserver -> Port
try:
    xbmc_port = int(config.get_setting("xbmc_puerto", "biblioteca"))
except:
    xbmc_port = 0
# Base URL of the json RPC calls. For GET calls we append a "request" URI
# parameter. For POSTs, we add the payload as JSON the the HTTP request body
xbmc_json_rpc_url = "http://" + xbmc_host + ":" + str(xbmc_port) + "/jsonrpc"


def mark_auto_as_watched(item):
    def mark_as_watched_subThread(item):
        logger.info()
        # logger.debug("item:\n" + item.tostring('\n'))

        condicion = config.get_setting("watched_setting", "biblioteca")

        xbmc.sleep(5000)

        sync_with_trakt = False

        while platformtools.is_playing():
            tiempo_actual = xbmc.Player().getTime()
            totaltime = xbmc.Player().getTotalTime()

            mark_time = 0
            if condicion == 0:  # '5 minutos'
                mark_time = 300
            elif condicion == 1:  # '30%'
                mark_time = totaltime * 0.3
            elif condicion == 2:  # '50%'
                mark_time = totaltime * 0.5
            elif condicion == 3:  # '80%'
                mark_time = totaltime * 0.8

            # logger.debug(str(tiempo_actual))
            # logger.debug(str(mark_time))

            if tiempo_actual > mark_time:
                item.playcount = 1
                sync_with_trakt = True
                from channels import biblioteca
                biblioteca.mark_content_as_watched(item)
                break

            xbmc.sleep(30000)

        # Sincronizacion silenciosa con Trakt
        if sync_with_trakt:
            if config.get_setting("sync_trakt_watched", "biblioteca"):
                sync_trakt()

    # Si esta configurado para marcar como visto
    if config.get_setting("mark_as_watched", "biblioteca"):
        Thread(target=mark_as_watched_subThread, args=[item]).start()


def sync_trakt(silent=True):

    # Para que la sincronizacion no sea silenciosa vale con silent=False
    if xbmc.getCondVisibility('System.HasAddon("script.trakt")'):
        notificacion = True
        if (not config.get_setting("sync_trakt_notification", "biblioteca") and
                platformtools.is_playing()):
            notificacion = False

        xbmc.executebuiltin('RunScript(script.trakt,action=sync,silent=%s)' % silent)
        logger.info("Sincronizacion con Trakt iniciada")

        if notificacion:
            platformtools.dialog_notification("pelisalacarta",
                                              "Sincronizacion con Trakt iniciada",
                                              icon=0,
                                              time=2000)


def mark_content_as_watched_on_kodi(item, value=1):
    """
    marca el contenido como visto o no visto en la libreria de Kodi
    @type item: item
    @param item: elemento a marcar
    @type value: int
    @param value: >0 para visto, 0 para no visto
    """
    logger.info()
    # logger.debug("item:\n" + item.tostring('\n'))
    payload_f = ''

    if item.contentType == "movie":
        movieid = 0
        payload = {"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies",
                   "params": {"properties": ["title", "playcount", "originaltitle", "file"]},
                   "id": 1}

        data = get_data(payload)
        if 'result' in data and "movies" in data['result']:

            filename = filetools.basename(item.strm_path)
            head, tail = filetools.split(filetools.split(item.strm_path)[0])
            path = filetools.join(tail, filename)

            for d in data['result']['movies']:
                if d['file'].replace("/", "\\").endswith(path.replace("/", "\\")):
                    # logger.debug("marco la pelicula como vista")
                    movieid = d['movieid']
                    break

        if movieid != 0:
            payload_f = {"jsonrpc": "2.0", "method": "VideoLibrary.SetMovieDetails", "params": {
                "movieid": movieid, "playcount": value}, "id": 1}

    else:  # item.contentType != 'movie'
        episodeid = 0
        payload = {"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes",
                   "params": {"properties": ["title", "playcount", "showtitle", "file", "tvshowid"]},
                   "id": 1}

        data = get_data(payload)
        if 'result' in data and "episodes" in data['result']:

            filename = filetools.basename(item.strm_path)
            head, tail = filetools.split(filetools.split(item.strm_path)[0])
            path = filetools.join(tail, filename)

            for d in data['result']['episodes']:

                if d['file'].replace("/", "\\").endswith(path.replace("/", "\\")):
                    # logger.debug("marco el episodio como visto")
                    episodeid = d['episodeid']
                    break

        if episodeid != 0:
            payload_f = {"jsonrpc": "2.0", "method": "VideoLibrary.SetEpisodeDetails", "params": {
                "episodeid": episodeid, "playcount": value}, "id": 1}

    if payload_f:
        # Marcar como visto
        data = get_data(payload_f)
        # logger.debug(str(data))
        if data['result'] != 'OK':
            logger.error("ERROR al poner el contenido como visto")


def mark_season_as_watched_on_kodi(item, value=1):
    """
        marca toda la temporada como vista o no vista en la libreria de Kodi
        @type item: item
        @param item: elemento a marcar
        @type value: int
        @param value: >0 para visto, 0 para no visto
        """
    logger.info()
    # logger.debug("item:\n" + item.tostring('\n'))

    # Solo podemos marcar la temporada como vista en la BBDD de Kodi si la BBDD es local,
    # en caso de compartir BBDD esta funcionalidad no funcionara
    if modo_cliente:
        return

    if value == 0:
        value = 'Null'

    request_season = ''
    if item.contentSeason > -1:
        request_season = ' and c12= %s' % item.contentSeason

    item_path1 = "%" + item.path.replace("\\\\", "\\").replace(TVSHOWS_PATH, "")
    if item_path1[:-1] != "\\":
        item_path1 += "\\"
    item_path2 = item_path1.replace("\\", "/")

    sql = 'update files set playCount= %s where idFile  in ' \
          '(select idfile from episode_view where strPath like "%s" or strPath like "%s"%s)' % \
          (value, item_path1, item_path2, request_season)

    execute_sql_kodi(sql)

def get_data(payload):
    """
    obtiene la información de la llamada JSON-RPC con la información pasada en payload
    @type payload: dict
    @param payload: data
    :return:
    """
    logger.info("payload %s" % payload)
    # Required header for XBMC JSON-RPC calls, otherwise you'll get a 415 HTTP response code - Unsupported media type
    headers = {'content-type': 'application/json'}

    if modo_cliente:
        try:
            req = urllib2.Request(xbmc_json_rpc_url, data=jsontools.dump_json(payload), headers=headers)
            f = urllib2.urlopen(req)
            response = f.read()
            f.close()

            logger.info("get_data: response %s" % response)
            data = jsontools.load_json(response)
        except Exception, ex:
            template = "An exception of type {0} occured. Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            logger.info("get_data: error en xbmc_json_rpc_url: %s" % message)
            data = ["error"]
    else:
        try:
            data = jsontools.load_json(xbmc.executeJSONRPC(jsontools.dump_json(payload)))
        except Exception, ex:
            template = "An exception of type {0} occured. Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            logger.info("get_data:: error en xbmc.executeJSONRPC: {0}".
                        format(message))
            data = ["error"]

    logger.info("get_data: data %s" % data)

    return data


def update(content_type=FOLDER_TVSHOWS, folder=""):
    """
    Actualiza la libreria dependiendo del tipo de contenido y la ruta que se le pase.

    @type content_type: str
    @param content_type: tipo de contenido para actualizar, series o peliculas
    @type folder: str
    @param folder: nombre de la carpeta a escanear.
    """
    logger.info()

    librarypath = config.get_library_config_path()

    # Si termina en "/" lo eliminamos
    if librarypath.endswith("/"):
        librarypath = librarypath[:-1]

    if librarypath.startswith("special:"):
        if not librarypath.endswith(content_type):
            librarypath += "/" + content_type
        if folder:
            librarypath += "/" + folder
    else:
        if not librarypath.endswith(content_type):
            librarypath = filetools.join(librarypath, content_type)
        if folder:
            librarypath = filetools.join(librarypath, folder)


    # Añadimos el caracter finalizador
    if not librarypath.endswith("/"):
        librarypath += "/"

    # Comprobar que no se esta buscando contenido en la biblioteca de Kodi
    while xbmc.getCondVisibility('Library.IsScanningVideo()'):
        xbmc.sleep(500)

    payload = {"jsonrpc": "2.0", "method": "VideoLibrary.Scan", "params": {"directory": librarypath}, "id": 1}
    data = get_data(payload)
    logger.info("data: %s" % data)


def clean(mostrar_dialogo=False):
    """
    limpia la libreria de elementos que no existen
    @param mostrar_dialogo: muestra el cuadro de progreso mientras se limpia la biblioteca
    @type mostrar_dialogo: bool
    """
    logger.info()
    payload = {"jsonrpc": "2.0", "method": "VideoLibrary.Clean", "id": 1,
               "params": {"showdialogs": mostrar_dialogo}}
    data = get_data(payload)
    logger.info("data: %s" % data)


def establecer_contenido(content_type, silent=False):
    if config.is_xbmc():
        continuar = False
        msg_text = "Ruta Biblioteca personalizada"

        librarypath = config.get_setting("librarypath")
        if librarypath == "special://profile/addon_data/plugin.video.pelisalacarta/library":
            continuar = True
            if content_type == FOLDER_MOVIES:
                if not xbmc.getCondVisibility('System.HasAddon(metadata.themoviedb.org)'):
                    if not silent:
                        # Preguntar si queremos instalar metadata.themoviedb.org
                        install = platformtools.dialog_yesno("The Movie Database",
                                                             "No se ha encontrado el Scraper de películas de TheMovieDB.",
                                                             "¿Desea instalarlo ahora?")
                    else:
                        install = True

                    if install:
                        try:
                            # Instalar metadata.themoviedb.org
                            xbmc.executebuiltin('xbmc.installaddon(metadata.themoviedb.org)', True)
                            logger.info("Instalado el Scraper de películas de TheMovieDB")
                        except:
                            pass

                    continuar = (install and xbmc.getCondVisibility('System.HasAddon(metadata.themoviedb.org)'))
                    if not continuar:
                        msg_text = "The Movie Database no instalado."

            else: # SERIES
                # Instalar The TVDB
                if not xbmc.getCondVisibility('System.HasAddon(metadata.tvdb.com)'):
                    if not silent:
                        # Preguntar si queremos instalar metadata.tvdb.com
                        install = platformtools.dialog_yesno("The TVDB",
                                                             "No se ha encontrado el Scraper de series de The TVDB.",
                                                             "¿Desea instalarlo ahora?")
                    else:
                        install = True

                    if install:
                        try:
                            # Instalar metadata.tvdb.com
                            xbmc.executebuiltin('xbmc.installaddon(metadata.tvdb.com)', True)
                            logger.info("Instalado el Scraper de series de The TVDB")
                        except:
                            pass

                    continuar = (install and xbmc.getCondVisibility('System.HasAddon(metadata.tvdb.com)'))
                    if not continuar:
                        msg_text = "The TVDB no instalado."

                # Instalar TheMovieDB
                if continuar and not xbmc.getCondVisibility('System.HasAddon(metadata.tvshows.themoviedb.org)'):
                    continuar = False
                    if not silent:
                        # Preguntar si queremos instalar metadata.tvshows.themoviedb.org
                        install = platformtools.dialog_yesno("The Movie Database",
                                                             "No se ha encontrado el Scraper de series de TheMovieDB.",
                                                             "¿Desea instalarlo ahora?")
                    else:
                        install = True

                    if install:
                        try:
                            # Instalar metadata.tvshows.themoviedb.org
                            # 1º Probar desde el repositorio ...
                            xbmc.executebuiltin('xbmc.installaddon(metadata.tvshows.themoviedb.org)', True)
                            if not xbmc.getCondVisibility('System.HasAddon(metadata.tvshows.themoviedb.org)'):
                                    # ...si no funciona descargar e instalar desde la web
                                    url = "http://mirrors.kodi.tv/addons/jarvis/metadata.tvshows.themoviedb.org/metadata.tvshows.themoviedb.org-1.3.1.zip"
                                    path_down = xbmc.translatePath(
                                        "special://home/addons/packages/metadata.tvshows.themoviedb.org-1.3.1.zip")
                                    path_unzip = xbmc.translatePath("special://home/addons/")
                                    header = ("User-Agent",
                                              "Kodi/15.2 (Windows NT 10.0; WOW64) App_Bitness/32 Version/15.2-Git:20151019-02e7013")

                                    from core import downloadtools
                                    from core import ziptools

                                    downloadtools.downloadfile(url, path_down, continuar=True, headers=[header])
                                    unzipper = ziptools.ziptools()
                                    unzipper.extract(path_down, path_unzip)
                                    xbmc.executebuiltin('UpdateLocalAddons')

                            strSettings = '<settings>\n' \
                                          '    <setting id="fanart" value="true" />\n' \
                                          '    <setting id="keeporiginaltitle" value="false" />\n' \
                                          '    <setting id="language" value="es" />\n' \
                                          '</settings>'
                            path_settings = xbmc.translatePath("special://profile/addon_data/metadata.tvshows.themoviedb.org/settings.xml")
                            tv_themoviedb_addon_path = filetools.dirname(path_settings)
                            if not filetools.exists(tv_themoviedb_addon_path):
                                filetools.mkdir(tv_themoviedb_addon_path)
                            if filetools.write(path_settings,strSettings):
                                continuar = True

                        except:
                            pass

                    continuar = (install and continuar)
                    if not continuar:
                        msg_text = "The Movie Database no instalado."

            idPath = 0
            idParentPath = 0
            strPath = ""
            if continuar:
                continuar = False
                librarypath = config.get_library_config_path()
                if not librarypath.endswith("/"):
                    librarypath = librarypath + "/"

                # Buscamos el idPath
                sql = 'SELECT MAX(idPath) FROM path'
                nun_records, records = execute_sql_kodi(sql)
                if nun_records == 1:
                    idPath = records[0][0] + 1


                # Buscamos el idParentPath
                sql = 'SELECT idPath, strPath FROM path where strPath LIKE "%s"' % \
                                            librarypath.replace('/profile/', '/%/').replace('/home/userdata/', '/%/')
                nun_records, records = execute_sql_kodi(sql)
                if nun_records == 1:
                    idParentPath = records[0][0]
                    librarypath = records[0][1]
                    continuar = True
                else:
                    # No existe librarypath en la BD: la insertamos
                    sql = 'INSERT INTO path (idPath, strPath,  scanRecursive, useFolderNames, noUpdate, exclude) VALUES ' \
                          '(%s, "%s", 0, 0, 0, 0)' % (idPath, librarypath)
                    nun_records, records = execute_sql_kodi(sql)
                    if nun_records == 1:
                        continuar = True
                        idParentPath = idPath
                        idPath += 1
                    else:
                        msg_text = "Error al fijar librarypath en BD"

            if continuar:
                continuar = False

                # Fijamos strContent, strScraper, scanRecursive y strSettings
                if content_type == FOLDER_MOVIES:
                    strContent = 'movies'
                    strScraper = 'metadata.themoviedb.org'
                    scanRecursive = 2147483647
                    strSettings = "<settings><setting id='RatingS' value='TMDb' /><setting id='certprefix' value='Rated ' />" \
                                  "<setting id='fanart' value='true' /><setting id='keeporiginaltitle' value='false' />" \
                                  "<setting id='language' value='es' /><setting id='tmdbcertcountry' value='us' />" \
                                  "<setting id='trailer' value='true' /></settings>"
                    strActualizar = "¿Desea configurar este Scraper en español como opción por defecto para películas?"

                else:
                    strContent = 'tvshows'
                    strScraper = 'metadata.tvdb.com'
                    scanRecursive = 0
                    strSettings = "<settings><setting id='RatingS' value='TheTVDB' />" \
                                  "<setting id='absolutenumber' value='false' />" \
                                  "<setting id='dvdorder' value='false' />" \
                                  "<setting id='fallback' value='true' />" \
                                  "<setting id='fanart' value='true' />" \
                                  "<setting id='language' value='es' /></settings>"
                    strActualizar = "¿Desea configurar este Scraper en español como opción por defecto para series?"

                # Fijamos strPath
                strPath = librarypath + content_type + "/"
                logger.info("%s: %s" % (content_type, strPath))

                # Comprobamos si ya existe strPath en la BD para evitar duplicados
                sql = 'SELECT idPath FROM path where strPath="%s"' % strPath
                nun_records, records = execute_sql_kodi(sql)
                sql = ""
                if nun_records == 0:
                    # Insertamos el scraper
                    sql = 'INSERT INTO path (idPath, strPath, strContent, strScraper, scanRecursive, useFolderNames, ' \
                          'strSettings, noUpdate, exclude, idParentPath) VALUES (%s, "%s", "%s", "%s", %s, 0, ' \
                          '"%s", 0, 0, %s)' % (
                          idPath, strPath, strContent, strScraper, scanRecursive, strSettings, idParentPath)
                else:
                    if not silent:
                        # Preguntar si queremos configurar themoviedb.org como opcion por defecto
                        actualizar = platformtools.dialog_yesno("The TVDB", strActualizar)
                    else:
                        actualizar = True

                    if actualizar:
                        # Actualizamos el scraper
                        idPath = records[0][0]
                        sql = 'UPDATE path SET strContent="%s", strScraper="%s", scanRecursive=%s, strSettings="%s" ' \
                              'WHERE idPath=%s' % (strContent, strScraper, scanRecursive, strSettings, idPath)

                if sql:
                    nun_records, records = execute_sql_kodi(sql)
                    if nun_records == 1:
                        continuar = True

                if not continuar:
                    msg_text = "Error al configurar el scraper en la BD."


        if not continuar:
            heading = "Biblioteca no %s configurada" % content_type
            #msg_text = "Asegurese de tener instalado el scraper de The Movie Database"
        elif content_type == FOLDER_TVSHOWS and not xbmc.getCondVisibility('System.HasAddon(metadata.tvshows.themoviedb.org)'):
            heading = "Biblioteca %s configurada" % content_type
            msg_text = "Es necesario reiniciar Kodi para que los cambios surtan efecto."
        else:
            heading = "Biblioteca %s configurada" % content_type
            msg_text = "Felicidades la biblioteca de Kodi ha sido configurada correctamente."
        platformtools.dialog_notification(heading, msg_text, icon=1, time=10000)
        logger.info("%s: %s" % (heading,msg_text))
