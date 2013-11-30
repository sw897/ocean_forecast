#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import math
import datetime
import  netCDF4
import numpy as np
import Image, ImageDraw, aggdraw

class Point(object):
    '''点类'''
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def __str__(self):
        return '%f, %f' % (self.x, self.y)

class RowCol(object):
    '''行列类: row:y, col:x'''
    def __init__(self, row, col):
        self.row = row
        self.col = col
    def __str__(self):
        return '%f, %f' % (self.row, self.col)

class LatLon(object):
    '''经纬度坐标点类'''
    DEG_TO_RAD = math.pi / 180
    RAD_TO_DEG = 180 / math.pi
    MAX_MARGIN = 1.0E-9
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon
    def equals(self, obj):
        margin = math.max(math.abs(self.lat - obj.lat),math.abs(self.lon - obj.lon))
        return margin <= self.MAX_MARGIN
    def __str__(self):
        return '%f, %f' % (self.lat, self.lon)

class IProjection(object):
    '''投影接口'''
    @classmethod
    def project(cls, latlon):
        pass
    @classmethod
    def unproject(cls, point):
        pass

class WebMercatorProjection(IProjection):
    '''Web墨卡托投影'''
    MAX_LATITUDE = 85.0511287798
    @classmethod
    def project(cls, latlon):
        d = LatLon.DEG_TO_RAD
        maxlat = cls.MAX_LATITUDE
        lat = max(min(maxlat, latlon.lat), -maxlat)
        x = latlon.lon * d
        y = lat * d
        y = math.log(math.tan((math.pi / 4) + (y / 2)))
        return Point(x, y)
    @classmethod
    def unproject(cls, point):
        d = LatLon.RAD_TO_DEG
        lon = point.x * d
        lat = (2 * math.atan(math.exp(point.y)) - (math.pi / 2)) * d
        return LatLon(lat, lon);

class LatLonProjection(IProjection):
    '''经纬度投影(本质是非投影坐标参考,在可视化时强制二维化)'''
    @classmethod
    def project(cls, latlon):
        return Point(latlon.lon, latlon.lat)
    @classmethod
    def unproject(cls, point):
        return LatLon(point.y, point.x)

class MercatorProjction(IProjection):
    '''横轴墨卡托投影'''
    pass

class TileCoord(object):
    '''瓦片坐标类'''
    def __init__(self, z, y, x, n=8):
        self.z = z
        self.y = y
        self.x = x
        self.n = n #切分子格网个数

    def __cmp__(self, other):
        return cmp(self.n, other.n) or cmp(self.z, other.z) or cmp(self.x, other.x) or cmp(self.y, other.y)

    def __repr__(self):  # pragma: no cover
        if self.n == 1:
            return '%s(%r, %r, %r)' % (self.__class__.__name__,
                                       self.z, self.x, self.y)
        else:
            return '%s(%r, %r, %r, %r)' % (self.__class__.__name__,
                                           self.z, self.x, self.y, self.n)

    def __str__(self):
        if self.n == 1:
            return '%d/%d/%d' % (self.z, self.y, self.x)
        else:
            return '%d/%d/%d:+%d/+%d' % (self.z, self.y, self.x, self.n, self.n)

    def tuple(self):
        return (self.z, self.y, self.x, self.n)

    @classmethod
    def from_string(cls, s):
        m = re.match(r'(\d+)/(\d+)/(\d+)(?::\+(\d+)/\+\4)?\Z', s)
        if not m:
            raise ValueError('invalid literal for %s.from_string: %r' % (cls.__name__, s))
        x, y, z, n = m.groups()
        return cls(int(x), int(y), int(z), int(n) if n else 1)

    @classmethod
    def from_tuple(cls, tpl):
        return cls(*tpl)

    #根据投影获取瓦片对应的范围
    def get_bbox(self, projection=LatLonProjection):
        worldextent = WorldExtent(projection)
        resolution = worldextent.resolution / math.pow(2, self.z)
        xmin = resolution * self.x + worldextent.xmin
        ymax = worldextent.ymax - resolution * self.y
        xmax = xmin + resolution
        ymin = ymax - resolution
        return [xmin, ymin, xmax, ymax]

    #根据投影切分瓦片，返回地理坐标迭代器
    def iter_points(self, projection=LatLonProjection):
        worldextent = WorldExtent(projection)
        resolution = worldextent.resolution / math.pow(2, self.z)
        new_res = resolution / self.n
        xmin = resolution * self.x + worldextent.xmin
        ymax = worldextent.ymax - resolution * self.y
        for i in xrange(0, self.n):
            for j in xrange(0, self.n):
                yield projection.unproject(Point(xmin+new_res/2.+new_res*j, ymax-new_res/2.-new_res*i)) # 取格网中心点

    #返回子块的迭代器
    def iter_coords(self):
        for i in xrange(0, self.n):
            for j in xrange(0, self.n):
                yield (j, i)

class WorldExtent(object):
    '''世界范围与0级切片尺寸'''
    def __init__(self, projection=LatLonProjection):
        if projection == WebMercatorProjection:
            self.xmin = -math.pi
            self.xmax = math.pi
            self.ymin = -math.pi
            self.ymax = math.pi
            self.resolution = 2*math.pi
        elif projection == LatLonProjection:
            self.xmin = -180
            self.xmax = 180
            self.ymin = -90
            self.ymax = 90
            self.resolution = 180
        else:
            pass

class Extent(object):
    '''范围类'''
    def __init__(self, xmin, ymin, xmax, ymax, projection=LatLonProjection):
        self.xmin = xmin
        self.ymin = ymin
        self.xmax = xmax
        self.ymax = ymax
        self.projection = projection

    def __str__(self):
        return '%f, %f, %f, %f' % (self.xmin, self.ymin, self.xmax, self.ymax)

    def tuple(self):
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @classmethod
    def from_string(cls, s):
        m = re.match(r'(\f+), (\f+), (\f+), (\f+)', s)
        if not m:
            raise ValueError('invalid literal for %s.from_string: %r' % (cls.__name__, s))
        xmin, ymin, xmax, ymax = m.groups()
        return cls(float(xmin), float(ymin), float(xmax), float(ymax))

    @classmethod
    def from_tuple(cls, tpl):
        return cls(*tpl)

    #投影变换
    def transform(self, projection):
        if self.projection == projection:
            return self
        else:
            point1 = Point(self.xmin, self.ymin)
            point2 = Point(self.xmax, self.ymax)
            latlon1 = self.projection.unproject(point1)
            latlon2 = self.projection.unproject(point2)
            point1 = projection.project(latlon1)
            point2 = projection.project(latlon2)
            return Extent(point1.x, point1.y, point2.x, point2.y, projection)

    #获取指定投影下的瓦片序列
    def iter_tilecoords(self, level, projection):
        extent = self
        if self.projection != projection:
            extent = self.transform(projection)
        worldextent = WorldExtent(projection)
        nums = pow(2, level)
        col_min = int((extent.xmin - worldextent.xmin)/worldextent.resolution * nums)
        col_max = int((extent.xmax - worldextent.xmin)/worldextent.resolution * nums)
        row_min = int((worldextent.ymax - extent.ymax)/worldextent.resolution * nums)
        row_max = int((worldextent.ymax - extent.ymin)/worldextent.resolution * nums)
        for row in range(row_min, row_max+1):
            for col in range(col_min, col_max + 1):
                yield TileCoord(level, row, col)

    #不改变投影，直接按行列取值
    def iter_grid_points(self, rows, cols):
        res_lat = (self.ymax - self.ymin)/rows
        res_lon = (self.xmax - self.xmin)/cols
        for row in range(rows):
            for col in range(cols):
                yield Point(self.xmin + res_lon*col, self.ymin + res_lat*row)

class SimpleLineStyle(object):
    color = (255, 255, 255)
    width = 1

class MarineSymbol(object):
    def __init__(self, value, angle):
        self.value = float(value)
        self.angle = float(angle)

    def zoom(self, scale):
        self.points = self.points*scale
        if hasattr(self, 'polygon'):
            self.polygon = self.polygon*scale

    def pan(self, pos):
        for i, point in enumerate(self.points):
            self.points[i] = point + pos
        if hasattr(self, 'polygon'):
            for i, point in enumerate(self.polygon):
                self.polygon[i] = point + pos

    def rotate(self, angle):
        xx = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        self.points = self.points.dot(xx)
        if hasattr(self, 'polygon'):
            self.polygon = self.polygon.dot(xx)

    def draw_agg(self, draw, style):
        pass

class WindSymbol(MarineSymbol):
    def __init__(self, value, angle):
        self.value = float(value)
        self.angle = float(angle)
        self.level = self.speed2level(self.value)
        self.size = 4
        if self.level < 9:
            points = np.array([[0, 4], [0, 0], [0, 0], [1, 0], [1, 0], [2, 0], [0, 1], [1, 1], [1, 1], [2, 1], [0, 2], [1, 2], \
                [1, 2], [2, 2], [0, 3], [1, 3], [1, 3], [2, 3]])
            self.points = points[0:2*(self.level+1)]
        else:
            self.points = np.array([[0, 4], [0, 0], [0, 0], [2, 2], [0, 2], [2, 2]])
        self.rotate(angle)
    def speed2level(self, speed):
        values = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.6, 32.6]
        for i in range(len(values)):
            if speed < values[i]:
                break
        return i

    def level2speed(self, level):
        values = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.6, 32.6]
        if level > len(values) - 1:
            level = len(values) - 1
        return values[level]

    def draw_agg(self, draw, style):
        #draw.setantialias(True)
        pen = aggdraw.Pen(tuple(style.color), style.width)
        for it in range(len(self.points)/2):
            draw.line(tuple(list(self.points[2*it]) + list(self.points[2*it+1])), pen)
        #draw.flush()

class ArrowSymbol(MarineSymbol):
    def __init__(self, value, angle):
        self.value = float(value)
        self.angle = float(angle)
        self.points = np.array([[0, 0], [0, 4]])
        self.polygon = np.array([[-.5, 1], [0, 0], [.5, 1]])
        self.size = 4
        self.rotate(angle)

    def segment_zoom(self, vs):
        if self.value < vs[1]:
            scale = .5
        elif self.value > vs[2]:
            scale = 1.
        else:
            scale = .5 + (self.value-vs[1])/(vs[2]-vs[1])
        self.points = self.points*scale

    def draw_agg(self, draw, style):
        #draw.setantialias(True)
        points = list(self.polygon[0]) + list(self.polygon[1]) + list(self.polygon[2]) + list(self.polygon[0])
        pen = aggdraw.Pen(tuple(style.color), style.width)
        brush = aggdraw.Brush(tuple(style.color))
        draw.polygon(tuple(points), pen, brush)
        draw.line(tuple(list(self.points[0]) + list(self.points[1])), pen)
        #draw.flush()

class NcArrayUtility(object):
    @classmethod
    def get_stats(cls, values):
        vmax = np.nanmax(values)
        vmin = np.nanmin(values)
        mean = np.nanmean(values)
        std = np.nanstd(values)
        return (vmax, vmin, mean, std)

    @classmethod
    def get_value_parts(cls, values):
        vmax = np.nanmax(values)
        vmin = np.nanmin(values)
        mean = np.nanmean(values)
        std = np.nanstd(values)
        times = 3
        vmax_fix = mean + times*std
        vmin_fix = mean - times*std
        vmax_fix = vmax if vmax < vmax_fix else vmax_fix
        vmin_fix = vmin if vmin > vmin_fix else vmin_fix
        vs = [vmin, vmin_fix, vmax_fix, vmax]
        return vs

    @classmethod
    def uv2va(cls, uv):
        if len(uv) != 2:
            return uv
        if math.isnan(uv[0]) or math.isnan(uv[1]):
            value = np.nan
            angle = np.nan
        else:
            value = math.sqrt(uv[0]*uv[0] + uv[1]*uv[1])
            if value == 0:
                angle = 0
            else:
                angle = math.acos(uv[0]/value)
                if uv[1] < 0:
                    angle = 2*math.pi - angle
        return [value, angle]

class HueGradient(object):
    @classmethod
    def value_to_hue(cls, v, vs, hs):
        if v > vs[2]:
            h1 = hs[2]
            h2 = hs[3]
            v1 = vs[2]
            v2 = vs[3]
        elif v < vs[1]:
            h1 = hs[0]
            h2 = hs[1]
            v1 = vs[0]
            v2 = vs[1]
        else:
            h1 = hs[1]
            h2 = hs[2]
            v1 = vs[1]
            v2 = vs[2]
        h = cls.nolinear_gradient(v, v1, v2, h1, h2)
        return h

    @classmethod
    def get_hue_parts(cls, vs):
        hs = [240, 230, 10, 0]
        if vs[1] == vs[0]:
            hs[1] = hs[0]
        if vs[2] == vs[3]:
            hs[2] = hs[3]
        return hs

    @classmethod
    def linear_gradient(cls, v, v1,v2,h1,h2):
        k = (h2-h1)*1./(v2-v1)
        return h1+(v-v1)*k

    #非线性插值, x 的2次方函数
    @classmethod
    def nolinear_gradient(cls, v, v1,v2,h1,h2):
        if v1 == v2:
            return h1
        x = (v-v1)*1./(v2-v1)*4
        if x < 2: y = math.pow(x, 2)
        else: y = 8 - math.pow(4-x, 2)
        return h1 +  (h2-h1)*y/8

class ColorModelUtility(object):
    @classmethod
    def hex2rgb(cls, hex):
        r = hex >> 16
        g = (hex >> 8) & 0xff
        b = hex & 0xff
        return (r, g, b)

    @classmethod
    def rgb2hex(cls, rgb):
        if rgb == None or len(rgb) != 3 or min(rgb) < 0 or max(rgb) > 255:
            return 0xFFFFFF
        return rgb[0] << 16 | rgb[1] << 8 | rgb[2]

    @classmethod
    def hsv2rgb(cls, hsv):
        h = float(hsv[0])
        s = float(hsv[1])
        v = float(hsv[2])
        h60 = h / 60.0
        h60f = math.floor(h60)
        hi = int(h60f) % 6
        f = h60 - h60f
        p = v * (1 - s)
        q = v * (1 - f * s)
        t = v * (1 - (1 - f) * s)
        r, g, b = 0, 0, 0
        if hi == 0: r, g, b = v, t, p
        elif hi == 1: r, g, b = q, v, p
        elif hi == 2: r, g, b = p, v, t
        elif hi == 3: r, g, b = p, q, v
        elif hi == 4: r, g, b = t, p, v
        elif hi == 5: r, g, b = v, p, q
        r, g, b = int(r * 255), int(g * 255), int(b * 255)
        return [r, g, b]

    @classmethod
    def rgb2hsv(cls, rgb):
        r, g, b = rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0
        mx = max(r, g, b)
        mn = min(r, g, b)
        df = mx-mn
        if mx == mn: h = 0
        elif mx == r: h = (60 * ((g-b)/df) + 360) % 360
        elif mx == g: h = (60 * ((b-r)/df) + 120) % 360
        elif mx == b: h = (60 * ((r-g)/df) + 240) % 360
        if mx == 0:s = 0
        else:s = df/mx
        v = mx
        return [h, s, v]

class TINStore(object):
    def __init__(self, date, region = 'NWP'):
        pass

    def get_capabilities(self):
        pass

    def get_capabilities2(self, variable, time, level):
        pass

    def is_valid_params(self):
        pass

    def get_value(self, variable = None, latlon = None, time = 0):
        pass

    def export_to_shapefile(self):
        pass

class FVCOMStore(TINStore):
    def __init__():
        self.no_data = -999.
        self.dimensions = {'lon' : 'longitude', 'lat' : 'latitude'}
        self.variables = {'u': 'u', 'v': 'v', 'zeta': 'zeta'}
        self.default_variables = ['u', 'v']
        regions = {
                            'BHE' : { 'times':72},
                            'QDH' : {'times':72},
                            'DLH' : {'times':72},
                            'RZG' : {'times':72},
                            'SD' : {'times':72},
                        }
        try:
            self.times = regions[region]['times']
            subdir = 'FVCOM_stm'
            regiondir = region
            subnames = [subdir, regiondir, str(date.year) + date.strftime("%m%d") + 'UTC', '180', '1hr']
            filename = '_'.join(subnames)
            self.ncfs = os.path.join(os.environ['NC_PATH'], subdir, filename)
            if not os.path.isdir(self.ncfs):
                os.mkdir(self.ncfs)
            ncfile = self.ncfs + '.nc'
            self.nc = netCDF4.Dataset(ncfile, 'r')
        except Exception, e:
            print e.__str__()

class GridStore(object):
    '''格网存储类'''

    def __init__(self, date, region):
        pass

    def get_capabilities(self):
        capabilities = {
            "region":self.region,
            "date":self.date,
            "dimensions":self.dimensions,
            "variables":self.variables,
            "default_variables":self.variables,
            "extent":str(self.extent),
            "times":self.times,
            "levels":self.levels,
            "resolution":self.resolution,
            "cols":self.cols,
            "rows":self.rows
        }
        return capabilities

    def get_capabilities2(self, variables, time, level):
        values = self.get_scalar_values(variables, time, level)
        vmax, vmin, mean, std = NcArrayUtility.get_stats(values)
        capabilities = {
            "variable":variable,
            "extent":str(self.extent),
            "time":time,
            "level":level,
            "resolution":self.resolution,
            "cols":self.cols,
            "rows":self.rows,
            "max":vmax,
            "min":vmin,
            "mean":mean,
            "std":std
         }
        return capabilities

    def get_colrow(self, latlon):
        if latlon is not None:
            lon_index = int(round((latlon.lon - self.extent.xmin) / self.resolution))
            lat_index = int(round((latlon.lat - self.extent.ymin) / self.resolution))
            return RowCol(lat_index, lon_index)
        else:
            return None

    def is_valid_params(self, rowcol = None, time = None, level = None):
        if rowcol != None:
            if rowcol.col < 0 or rowcol.col > self.cols-1 or rowcol.row < 0 or rowcol.row > self.rows-1:
                return False
        if time != None:
            if time < 0 or time > self.times - 1:
                return False
        if level != None:
            if level < 0 or level > self.levels -1:
                return False
        return True

    def filter_values(self, values):
        for v in values:
            if np.isnan(v):
                return False
        return True

    def filter_variables(self, variables, defaults = None):
        if defaults is None:
            defaults = self.default_variables
        if variables == 'default':
            variables = defaults
        else:
            variables = []
            temp = variables.split(',')
            for var in temp:
                var = var.strip()
                if var in self.variables:
                    variables.append(var)
            if len(variables) < 1:
                variables = defaults
        return variables


    def get_value(self, variable = None, latlon = None, time = 0, level = 0):
        rowcol = None
        if latlon is not None:
            rowcol = self.get_colrow(latlon)
        return self.get_value_direct(variable, rowcol, time, level)

    def get_value_direct(self, variable = None, rowcol = None, time = 0, level = 0):
        if not self.is_valid_params(rowcol, time, level):
            return np.nan
        if not (variable in self.variables):
            return np.nan
        value = self.get_variable(variable, rowcol, time, level)
        return value

    def get_variable(self, variable, rowcol, time, level):
        netcdf = self.nc
        variable =  self.variables[variable]
        nodata2nan = lambda x: np.nan if x == self.no_data else float(x)
        if rowcol is not None:
            if isinstance(self, ROMSStore):
                value = netcdf.variables[variable][time][level][rowcol.row][rowcol.col]
            else:
                value = netcdf.variables[variable][time][rowcol.row][rowcol.col]
            value = float(value)
            return nodata2nan(value)
        else:
            if isinstance(self, ROMSStore):
                value = netcdf.variables[variable][time][level]
            else:
                value = netcdf.variables[variable][time]
            # # masked array to nparray
            # if isinstance(value, np.ma.masked_array):
            #     value = value.data
            array_nodata2nan = np.vectorize(nodata2nan, otypes=[np.float])
            return array_nodata2nan(value)

    def get_scalar_values(self, variables=None, time=0, level=0):
        if variables == None:
            variables = self.default_variables
        if isinstance(variables, list):
            values = None
            for var in variables:
                val = self.get_value_direct(var, None, time, level)
                val = val[:self.rows, :self.cols]
                val = pow(val, 2)
                if values is None:
                    values = val
                else:
                    values += val
            values = pow(values, .5)
        else:
            values = self.get_value_direct(variables, None, time, level)
            values = values[:self.rows, :self.cols]
        return values

    def get_vector_values(self, variables=None, time=0, level=0):
        if variables == None:
            variables = self.default_variables
        values = []
        if isinstance(variables, list):
            for var in variables:
                val = self.get_value_direct(var, None, time, level)
                val = val[:self.rows, :self.cols]
                values.append(val)
        else:
            val = self.get_value_direct(variables, None, time, level)
            val = val[:self.rows, :self.cols]
            values.append(val)
        return values

    def get_scalar_image_filename(self, variables, time, level, projection):
        if projection == WebMercatorProjection:
            code = '3857'
        else:
            code = '4326'
        dirname = os.path.join(self.ncfs, ','.join(variables), code)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        filename = os.path.join(dirname,  "%d_%d" % (time, level) + '.png')
        return filename

    def get_legend_filename(self, variables, time, level):
        dirname = os.path.join(self.ncfs, ','.join(variables))
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        filename = os.path.join(dirname,  "legend_%d_%d" % (time, level) + '.png')
        return filename

    def get_tile_json_filename(self, tilecoord, variables, time, level, projection):
        if projection == WebMercatorProjection:
            code = '3857'
        else:
            code = '4326'
        dirname = os.path.join(self.ncfs, ','.join(variables), code, "%d_%d" % (time, level), str(tilecoord.z), str(tilecoord.y))
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        filename = os.path.join(dirname,  "%d" % tilecoord.x + '.json')
        return filename

    def get_tile_image_filename(self, tilecoord, variables, time, level, projection, postProcess = None):
        if projection == WebMercatorProjection:
            code = '3857'
        else:
            code = '4326'
        dirname = os.path.join(self.ncfs, ','.join(variables), code, "%d_%d" % (time, level), str(tilecoord.z), str(tilecoord.y))
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        filename = os.path.join(dirname,  "%d" % tilecoord.x + '.png')
        return filename

    def get_scalar_isoline(self, variable = None, time = 0, level = 0):
        pass

    def get_legend(self, variables = None, time = 0, level = 0):
        legend = self.get_legend_filename(variables, time, level)
        if not os.path.isfile(legend):
            legend = self.export_legend(variables, time, level)
        return legend

    def get_scalar_image(self, variables = None, time = 0, level = 0, projection = LatLonProjection, update = False):
        filename = self.get_scalar_image_filename(variables, time, level, projection)
        if not os.path.isfile(filename):
            update = True
        else:
            # todo:检查文件时效性
            pass
        if update:
            filename = self.scalar_to_image(variables, time, level, projection)
        return filename

    def get_tile_image(self, tilecoord, variables, time, level, projection, postProcess = None, update = False):
        if variables is None:
            variables = self.default_variables
        filename = self.get_tile_image_filename(tilecoord, variables, time, level, projection)
        if not os.path.isfile(filename):
            update = True
        else:
            # todo:检查文件时效性
            pass
        if update:
            filename = self.export_tile_image(tilecoord, variables, time, level, projection, postProcess)
        return filename

    def get_tile_json(self, tilecoord, variables, time, level, projection, postProcess = None, update = False):
        if variables is None:
            variables = self.default_variables
        filename = self.get_tile_json_filename(tilecoord, variables, time, level, projection)
        if not os.path.isfile(filename):
            update = True
        else:
            # todo:检查文件时效性
            pass
        if update:
            json = self.export_tile_json(tilecoord, variables, time, level, projection, postProcess)
            fp = open(filename, 'w')
            fp.write(json)
            fp.close()
        return filename

    def vector_to_grid_image(self, variables, time, level, projection):
        pass

    def vector_to_jit_image(self, variables, time, level, projection):
        pass

    def vector_to_lit_image(self, variables, time, level, projection):
        pass

    def vector_to_lic_image(self, variables, time, level, projection):
        pass

    def vector_to_ostr_image(self, variables, time, level, projection):
        pass

    def vector_to_gstr_image(self, variables, time, level, projection):
        pass

    def scalar_to_image(self, variables, time, level, projection):
        if variables == None:
            variables = self.default_variables
        values = self.get_scalar_values(variables, time, level)
        vs = NcArrayUtility.get_value_parts(values)
        hs = HueGradient.get_hue_parts(vs)

        if projection == LatLonProjection:
            width = self.cols
            height = self.rows
            size = (width, height)
            img = Image.new("RGBA", size)
            draw = aggdraw.Draw(img)
            draw.setantialias(True)
            for row in range(height):
                for col in range(width):
                    v = values[row, col]
                    if np.isnan(v):
                        continue
                    h = HueGradient.value_to_hue(v, vs, hs)
                    rgb = ColorModelUtility.hsv2rgb((h, 1., 1.))
                    pen = aggdraw.Pen(tuple(rgb), 1)
                    draw.rectangle((col, height-row, col+1, height-1-row), pen)
            draw.flush()
            del draw
            filename = self.get_scalar_image_filename(variables, time, level, projection)
            img.save(filename, "png")
            return filename
        else:
            org_min = LatLon(self.extent.ymin, self.extent.xmin)
            org_max = LatLon(org_min.lat + self.resolution*self.rows, org_min.lon + self.resolution*self.cols)
            new_min = WebMercatorProjection.project(org_min)
            new_max = WebMercatorProjection.project(org_max)
            width = self.cols
            org_height = self.rows
            height = (org_max.lon-org_min.lon)/(new_max.x-new_min.x)*(new_max.y - new_min.y)/(org_max.lat-org_min.lat)*width
            dy = (new_max.y - new_min.y)/height
            org_dy = (org_max.lat - org_min.lat)/org_height
            height = int(round(height))
            size = (width, height)
            img = Image.new("RGBA", size)
            draw = aggdraw.Draw(img)
            draw.setantialias(True)
            for row in range(height):
                pt = Point(0, row*dy+new_min.y)
                ll = WebMercatorProjection.unproject(pt)
                org_row = (ll.lat-org_min.lat)/org_dy
                for col in range(width):
                    v = values[org_row, col]
                    if np.isnan(v):
                        continue
                    h = HueGradient.value_to_hue(v, vs, hs)
                    rgb = ColorModelUtility.hsv2rgb((h, 1., 1.))
                    pen = aggdraw.Pen(tuple(rgb), 1)
                    draw.rectangle((col, height-row, col+1, height-1-row), pen)
            draw.flush()
            del draw
            filename = self.get_scalar_image_filename(variables, time, level, projection)
            img.save(filename, "png")
            return filename

    def scalar_isoline_to_image(self, variable = None, time = 0, level = 0, projection=LatLonProjection):
        pass

    def export_legend(self, variables, time, level):
        values = self.get_scalar_values(variables, time, level)
        vs = NcArrayUtility.get_value_parts(values)
        hs = HueGradient.get_hue_parts(vs)
        size = (204, 34)
        margin_x = 10
        margin_y = 3
        font_margin_x = -5
        font_margin_y = 3
        bar_x = 186
        bar_y = 12
        len_mark = 5
        font = aggdraw.Font('black', '/Library/Fonts/Georgia.ttf',10)
        black_pen = aggdraw.Pen('black')
        img = Image.new("RGBA", size)
        draw = aggdraw.Draw(img)
        draw.setantialias(True)
        # draw color bar
        for i in range(bar_x):
            h = HueGradient.nolinear_gradient(i, 0, bar_x, hs[0], hs[3])
            rgb = ColorModelUtility.hsv2rgb((h, 1., 1.))
            pen = aggdraw.Pen(tuple(rgb), 1)
            draw.line((i+margin_x,0+margin_y,i+margin_x,bar_y+margin_y), pen)
        # draw color bar bound
        draw.rectangle((0+margin_x, 0+margin_y, bar_x+margin_x, bar_y+margin_y), black_pen)
        # draw scalar marker
        mark_nums = 6
        step = int(round((vs[2]-vs[1])/mark_nums))
        if step < 1:
            step = 1
        pos1 = int((hs[1]-hs[0])*1./(hs[3]-hs[0])*bar_x)
        pos2 = int((hs[2]-hs[0])*1./(hs[3]-hs[0])*bar_x)
        for i in range(mark_nums):
            v = int(round(vs[1]+step*i))
            if v > vs[2]: break
            pos = (v-vs[1])*1./(vs[2]-vs[1])*(pos2-pos1) + pos1
            draw.line((pos+margin_x, bar_y+margin_y, pos+margin_x, bar_y+len_mark+margin_y), black_pen)
            draw.text((pos+margin_x+font_margin_x, bar_y+len_mark+font_margin_y+margin_y), str(v), font)
        # save
        draw.flush()
        del draw
        legend = self.get_legend_filename(variables, time, level)
        img.save(legend, "png")
        return legend

    def export_tile_image(self, tilecoord, variables, time, level, projection, postProcess = None):
        imagesize = 256
        v_values = self.get_vector_values(variables, time, level)
        values = None
        for val in v_values:
            val = pow(val, 2)
            if values is None: values = val
            else: values += val
        values = pow(values, .5)
        vs = NcArrayUtility.get_value_parts(values)
        hs = HueGradient.get_hue_parts(vs)
        size = (imagesize,imagesize)
        img = Image.new("RGBA", size)
        draw = aggdraw.Draw(img)
        draw.setantialias(True)
        it = -1
        for latlon in tilecoord.iter_points(projection):
            it += 1
            values = []
            rowcol = self.get_colrow(latlon)
            if rowcol.row < 0 or rowcol.col < 0: continue
            if rowcol.row > self.rows-1 or rowcol.col > self.cols-1: continue
            for i,v in enumerate(variables):
                values.append(v_values[i][rowcol.row, rowcol.col])
            #values = [self.get_value(variable, latlon, time, level) for variable in variables]
            bfilter = self.filter_values(values)
            if not bfilter: continue
            if postProcess is not None:
                values = postProcess(values)
            h = HueGradient.value_to_hue(values[0], vs, hs)
            if np.isnan(h): continue
            style = SimpleLineStyle()
            style.color = ColorModelUtility.hsv2rgb((h, 1., 1.))
            symbol = None
            if isinstance(self, WRFStore):
                symbol = WindSymbol(values[0], values[1])
                style.width = 2
            elif isinstance(self, ROMSStore) or isinstance(self, POMStore):
                symbol = ArrowSymbol(values[0], values[1])
                symbol.segment_zoom(vs)
            if symbol is not None:
                gridsize = imagesize/tilecoord.n
                scale = gridsize/2./symbol.size
                symbol.zoom(scale)
                i = it / tilecoord.n
                j = it % tilecoord.n
                pos_x = gridsize*j + gridsize/2.
                pos_y = gridsize*i + gridsize/2.
                symbol.pan(np.array([pos_x, pos_y]))
                symbol.draw_agg(draw, style)
        # save
        draw.flush()
        del draw
        tile = self.get_tile_image_filename(tilecoord, variables, time, level, projection)
        img.save(tile, "png")
        return tile

    def export_tile_json(self, tilecoord, variables, time, level, projection, postProcess = None):
        if variables is None:
            variables = self.default_variables
        json = '{"type":"FeatureCollection","features":['
        for latlon in tilecoord.iter_points(projection):
            values = [self.get_value(variable, latlon, time, level) for variable in variables]
            bfilter = self.filter_values(values)
            if not bfilter: continue
            if postProcess is not None:
                values = postProcess(values)
            str_val = ''
            for v in values:
                str_val += "%.2f" % v
                str_val += ','
            if str_val[-1] == ',':
                str_val = str_val[:-1]
            string = '{"type":"Feature","geometry":{"type":"Point","coordinates":[%.4f,%.4f]},"properties": {"value": [%s]}}' % \
                        (latlon.lon, latlon.lat, str_val)
            json += string + ','
        if json[-1] == ',':
            json = json[:-1]
        json += ']}'
        return json

    def export_point_json(self, latlon, variables = None, projection=LatLonProjection, postProcess = None):
        if variables is None:
            variables = self.default_variables
        json = '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[%f,%f]},"properties": {"value": [' % (lon, lat)
        values = []
        for level in range(self.levels):
            for time in range(self.times):
                for variable in variables:
                    value = self.get_value(variable, latlon, time, level)
                    values.append(value)
                    json += '%.6f' % value + ','
        if json[-1] == ',':
            json = json[:-1]
        json += ']}}'
        json += ']}'
        return json

    def export_to_shapefile(self, projection=LatLonProjection):
        pass

    def export_to_imagetiles(self, z, variables = None, time = 0, level = 0, projection=LatLonProjection, postProcess=None, update=False):
        if variables is None:
            variables = self.default_variables
        for tilecoord in self.extent.iter_tilecoords(z, projection):
            self.get_tile_image(tilecoord, variables, time, level, projection, postProcess, update)

    def export_to_jsontiles(self, z, variables = None, time = 0, level = 0, projection=LatLonProjection, postProcess=None, update=False):
        if variables is None:
            variables = self.default_variables
        for tilecoord in self.extent.iter_tilecoords(z, projection):
            self.get_tile_json(tilecoord, variables, time, level, projection, postProcess, update)

    def clean_cache(self):
        import shutil
        shutil.rmtree(self.ncfs)

class WRFStore(GridStore):
    def __init__(self, date, region = 'NWP'):
        self.no_data = 1e+30
        self.dimensions = {'lon' : 'longitude', 'lat' : 'latitude'}
        self.variables = {'u': 'u10m', 'v': 'v10m', 'slp': 'slp'}
        self.default_variables = ['u', 'v']
        regions = {
                            'NWP' : {'extent':[103.8, 14.5, 140.4, 48.58], 'times':72, 'levels':1, 'resolution':.12},
                            'NCS' : {'extent':[116., 28.5, 129., 42.5], 'times':72, 'levels':1, 'resolution':.04},
                            'QDSEA' : {'extent':[119., 35., 121.5, 36.5], 'times':72, 'levels':1, 'resolution':.01},
                        }
        try:
            self.region = region
            self.date = str(date.year) + date.strftime("%m%d")
            self.extent = Extent.from_tuple(regions[region]['extent'])
            self.times = regions[region]['times']
            self.levels = regions[region]['levels']
            self.resolution = regions[region]['resolution']
            subdir = 'WRF_met'
            regiondir = region
            if regiondir == 'QDSEA':
                regiondir = 'QDsea'
            subnames = [subdir, regiondir, self.date + 'UTC', '180', '1hr']
            filename = '_'.join(subnames)
            self.ncfs = os.path.join(os.environ['NC_PATH'], subdir, filename)
            if not os.path.isdir(self.ncfs):
                os.mkdir(self.ncfs)
            ncfile = self.ncfs + '.nc'
            self.nc = netCDF4.Dataset(ncfile, 'r')
            self.cols = len(self.nc.dimensions[self.dimensions['lon']])
            self.rows = len(self.nc.dimensions[self.dimensions['lat']])
        except Exception, e:
            print e.__str__()

class SWANStore(GridStore):
    def __init__(self, date, region = 'NWP'):
        self.no_data = -9. #-999.0 -> -9.
        self.dimensions = {'lon' : 'longitude', 'lat' : 'latitude'}
        self.variables = {'hs': 'hs', 'tm': 'tm', 'di': 'di'}
        self.default_variables = ['hs']
        regions = {
                        'NWP' : {'extent':[105., 15., 140., 47.], 'times':72, 'levels':1, 'resolution':.1},
                        'NCS' : {'extent':[117., 32., 127., 42.], 'times':72, 'levels':1, 'resolution':1/30.},
                        'QDSEA' : {'extent':[119.2958, 34.8958, 121.6042, 36.8042], 'times':72, 'levels':1, 'resolution':1/120.},
                    }
        try:
            self.region = region
            self.date = str(date.year) + date.strftime("%m%d")
            self.extent = Extent.from_tuple(regions[region]['extent'])
            self.times = regions[region]['times']
            self.levels = regions[region]['levels']
            self.resolution = regions[region]['resolution']
            subdir = 'SWAN_wav'
            dirmap = {'NWP':'nw', 'NCS':'nchina', 'QDSEA':'qdsea'}
            regiondir = region
            if regiondir == 'QDSEA':
                regiondir = 'QDsea'
            subnames = [subdir, regiondir, self.date + 'UTC', '120', '1hr']
            filename = '_'.join(subnames)
            self.ncfs = os.path.join(os.environ['NC_PATH'], subdir, dirmap[region], filename)
            if not os.path.isdir(self.ncfs):
                os.mkdir(self.ncfs)
            ncfile = self.ncfs + '.nc'
            self.nc = netCDF4.Dataset(ncfile, 'r')
            self.cols = len(self.nc.dimensions[self.dimensions['lon']])
            self.rows = len(self.nc.dimensions[self.dimensions['lat']])
        except Exception, e:
            print e.__str__()

class WW3Store(SWANStore):
    def __init__(self, date, region = 'NWP'):
        self.no_data = -9. #-999.0 -> -9.
        self.dimensions = {'lon' : 'longitude', 'lat' : 'latitude'}
        self.variables = {'hs': 'hs', 'tm': 'tm', 'di': 'di'}
        self.default_variables = ['hs']
        regions = {
                        'GLB': {'extent':[105., 15., 140., 47.], 'times':72, 'levels':1, 'resolution':.1},
                        'NWP': {'name':'西北太平洋', 'extent':[105., 15., 140., 47.], 'times':72, 'levels':1, 'resolution':.1},
                    }
        try:
            self.region = region
            self.date = str(date.year) + date.strftime("%m%d")
            self.extent = Extent.from_tuple(regions[region]['extent'])
            self.times = regions[region]['times']
            self.levels = regions[region]['levels']
            self.resolution = regions[region]['resolution']
            subdir = 'SWAN_wav'
            dirmap = {'GLB':'global', 'NWP':'nww3'}
            regiondir = region
            if regiondir == 'QDSEA':
                regiondir = 'QDsea'
            subnames = ['WW3_wav', regiondir, self.date + 'UTC', '120', '1hr']
            filename = '_'.join(subnames)
            self.ncfs = os.path.join(os.environ['NC_PATH'], subdir, dirmap[region], filename)
            if not os.path.isdir(self.ncfs):
                os.mkdir(self.ncfs)
            ncfile = self.ncfs + '.nc'
            self.nc = netCDF4.Dataset(ncfile, 'r')
            self.cols = len(self.nc.dimensions[self.dimensions['lon']])
            self.rows = len(self.nc.dimensions[self.dimensions['lat']])
        except Exception, e:
            print e.__str__()

class POMStore(GridStore):
    def __init__(self, date, region = 'ECS'):
        self.no_data = 0 #999.0 -> 0
        self.dimensions = {'lon' : 'longitude', 'lat' : 'latitude'}
        self.variables = {'u': 'u', 'v': 'v', 'el': 'el'}
        self.default_variables = ['u', 'v']
        regions = {
                        'BH' : {'extent':[117.5, 37.2, 122., 42.], 'times':72, 'levels':1, 'resolution':1/240.},
                        'ECS' : {'extent':[117.5, 24.5, 137., 42.], 'times':24, 'levels':1, 'resolution':1/30.},
                        'NCS' : {'extent':[117., 32., 127., 42.], 'times':72, 'levels':1, 'resolution':1/30.},
                    }
        try:
            self.region = region
            self.date = str(date.year) + date.strftime("%m%d")
            self.extent = Extent.from_tuple(regions[region]['extent'])
            self.times = regions[region]['times']
            self.levels = regions[region]['levels']
            self.resolution = regions[region]['resolution']
            subdir = 'ROMS_cur'
            regiondir = region
            if regiondir == 'QDSEA':
                regiondir = 'QDsea'
            if region == 'ECS':
                subnames = ['POM_crt', regiondir, self.date + '0000BJS', '072', '1hr']
            elif region == 'BH':
                subnames = ['POM_crt', regiondir, self.date + '0000BJS', 'a24', '1hr']
            else:
                subnames = ['POM_cut', regiondir, self.date + '00BJS', '072', '1hr']
            filename = '_'.join(subnames)
            self.ncfs = os.path.join(os.environ['NC_PATH'], subdir, filename)
            if not os.path.isdir(self.ncfs):
                os.mkdir(self.ncfs)
            ncfile = self.ncfs + '.nc'
            self.nc = netCDF4.Dataset(ncfile, 'r')
            self.cols = len(self.nc.dimensions[self.dimensions['lon']])
            self.rows = len(self.nc.dimensions[self.dimensions['lat']])
        except Exception, e:
            print e.__str__()

class ROMSStore(GridStore):
    def __init__(self, date, region = 'NWP'):
        self.no_data = 1e+37
        self.dimensions = {'lon' : 'xi_v', 'lat' : 'eta_u'}
        self.variables = {'u': 'u', 'v': 'v'}
        self.default_variables = ['u', 'v']
        regions = {
                        'NWP' : {'extent':[99., -9., 148., 42.], 'times':1, 'levels':25, 'resolution':.1},
                        'NCS' : {'extent':[117.5, 32., 127., 41.], 'times':96, 'levels':6, 'resolution':1/30.},
                        'QDSEA' : {'extent':[119., 35., 122., 37.], 'times':96, 'levels':6, 'resolution':.1/30.},
                    }
        try:
            self.region = region
            self.date = str(date.year) + date.strftime("%m%d")
            self.extent = Extent.from_tuple(regions[region]['extent'])
            self.times = regions[region]['times']
            self.levels = regions[region]['levels']
            self.resolution = regions[region]['resolution']
            subdir = 'ROMS_cur'
            regiondir = region
            if regiondir == 'QDSEA':
                regiondir = 'QDsea'
            subnames = ['ROMS_crt', regiondir, self.date + '0000BJS', '072', '1hr']
            filename = '_'.join(subnames)
            self.ncfs = os.path.join(os.environ['NC_PATH'], subdir, filename)
            if not os.path.isdir(self.ncfs):
                os.mkdir(self.ncfs)
            ncfile = self.ncfs + '.nc'
            self.nc = netCDF4.Dataset(ncfile, 'r')
            self.cols = len(self.nc.dimensions[self.dimensions['lon']])
            self.rows = len(self.nc.dimensions[self.dimensions['lat']])
        except Exception, e:
            print e.__str__()

