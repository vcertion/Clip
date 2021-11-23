#!/usr/bin/env python
# _*_ coding: utf-8 _*_
__author__ = 'zjm'
__date__ = '2021/9/14 18:06'

import operator
import numpy as np
from osgeo import gdal, gdal_array, osr, gdalnumeric
import shapefile
import sys
import pickle

try:
    import Image
    import ImageDraw
except:
    from PIL import Image, ImageDraw

def usage():
  print("""
  usage clip.py <geotif> <shp> <outgeotiff> [options]
  
    geotiff    (input)  geotif files
    shp        (input)  shapefile to clip the geotif 
    outgeotiff (output) the clipped geotif files
""")
  sys.exit(-1)
  

def image2Array(i):
    """
    将一个Python图像库的数组转换为一个gdal_array图片
    """
    a = gdal_array.numpy.frombuffer(i.tobytes(), 'b')
    a.shape = i.im.size[1], i.im.size[0]
    return a


def world2Pixel(geoMatrix, x, y):
    """
    使用GDAL库的geomatrix对象((gdal.GetGeoTransform()))计算地理坐标的像素位置
    """
    ulx = geoMatrix[0]
    uly = geoMatrix[3]
    xDist = geoMatrix[1]
    yDist = geoMatrix[5]
    rtnX = geoMatrix[2]
    rtnY = geoMatrix[4]
    pixel = int((x - ulx) / xDist)
    line = int((uly - y) / abs(yDist))
    return (pixel, line)

def pixel2World(geoMatrix,xSize,ySize):
    x=geoMatrix[0]+ySize*geoMatrix[1]-geoMatrix[1]/2
    y=geoMatrix[3]+xSize*geoMatrix[5]-geoMatrix[5]/2
    return (x,y)

def OpenArray(array, prototype_ds = None, xoff=0, yoff=0):
    ds = gdal_array.OpenArray(array)
    if ds is not None and prototype_ds is not None:
        if type(prototype_ds).__name__ == 'str':
            prototype_ds = gdal.Open(prototype_ds)
        if prototype_ds is not None:
            gdal_array.CopyDatasetInfo(prototype_ds, ds, xoff=xoff, yoff=yoff)
    return ds

def getBounds(geoMatrix, xSize, ySize):
    listx=[]
    listy=[]
    x1,y1=pixel2World(geoMatrix,0,0)
    x2,y2=pixel2World(geoMatrix,xSize,ySize)
    listx=[x1,x2]
    listy=[y1,y2]
    return (listx, listy)

def test(shapefile, geoTrans, srcImage):
    list_shape=[]
    list_point=[]

    maxX=-190
    minX=190
    maxY=-91
    minY=91

    nXsize = srcImage.RasterXSize
    nYsize = srcImage.RasterYSize

    listx, listy=getBounds(geoTrans, nYsize, nXsize)

    shapeNum=shapefile.numRecords
    for i in range(0, shapeNum):
        Nparts = len(shapefile.shape(i).parts)
        index = shapefile.shape(i).parts
        Npoints = len(shapefile.shape(i).points)
        index.append(Npoints)
        for j in range(Nparts):
            for k in range(index[j], index[j + 1]):
                list = shapefile.shape(i).points[k]
                if max(listx) < list[0] or list[0] < min(listx) or max(listy) < list[1] or list[1] < min(listy):
                    continue
                else:
                    if list[0]>maxX:
                        maxX=list[0]
                    elif list[0]<minX :
                        minX=list[0]
                    if list[1]>maxY:
                        maxY=list[1]
                    elif list[1]<minY:
                        minY=list[1]
                    list_shape.append(i)
                    list_point.append(k)
    return (list_shape,list_point,maxX,minX,maxY,minY)


def main():

    print('*** Clip the geotif file using the shapefile ***')
    print('*** Copyright 2021 Jianmin Zhou, v1.0 14-Sep-2021 ***')
    if len(sys.argv) < 3:
      usage()
    
	# 将数据源作为gdal_array载入
    raster = sys.argv[1] #tif路径
    shp = sys.argv[2]    #shp文件路径
    output = sys.argv[3] #输出路径
    srcArray = gdal_array.LoadFile(raster)
    #print(f'Data width (samples):{srcArray.shape}')
	
    # 同时载入gdal库的图片从而获取geotransform
    srcImage = gdal.Open(raster)
    geoTrans = srcImage.GetGeoTransform()

    # 使用PyShp库打开shp文件
    r = shapefile.Reader(shp)
    #print(r.shape())
    shapes = r.shapes()
    recds = r.records()
    ShpNum = r.numRecords


    #shp筛选
    list_shape,list_point,maxX,minX,maxY,minY=test(r,geoTrans,srcImage)
    set_shape=set(list_shape)
    shape_number=len(set_shape)

    #print(ShpNum)
    #for i in recds:
       #print (i)
    # 将图层扩展转换为图片像素坐标
    ulX, ulY = world2Pixel(geoTrans, minX, maxY)
    lrX, lrY = world2Pixel(geoTrans, maxX, minY)
    # 计算新图片的尺寸
    pxWidth = int(lrX - ulX)
    pxHeight = int(lrY - ulY)
    clip = srcArray[ulY:lrY, ulX:lrX]
	#Create pixel offset to pass to new image Projection info
    xoffset = ulX
    yoffset = ulY
    #print("Xoffset, Yoffset = (%f, %f)" % (xoffset, yoffset))
    # 为图片创建一个新的geomatrix对象以便附加地理参照数据
    geoTrans = list(geoTrans)
    geoTrans[0] = minX
    geoTrans[3] = maxY
    # 在一个空白的8字节黑白掩膜图片上把点映射为像元绘制边界线&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&
    MASK = np.ones((pxHeight, pxWidth), dtype='b')
    for i in range(0, ShpNum):
        if i in set_shape:
            mask_part = np.zeros((pxHeight, pxWidth), dtype='b')
            Nparts = len(r.shape(i).parts)
            #print(Nparts)
            index = r.shape(i).parts
            #print(index)
            Npoints = len(r.shape(i).points)
            index.append(Npoints)
            for j in range(Nparts):
                pixels = []
                for k in range(index[j], index[j+1]):
                    p = r.shape(i).points[k] ########################################
                    pixels.append(world2Pixel(geoTrans, p[0], p[1]))
                 #print(pixels.append)
                #print(geoTrans[5])
                if (j == 0):
                    rasterPoly = Image.new("L", (pxWidth, pxHeight), 1)
                    # 使用PIL创建一个空白图片用于绘制多边形
                    rasterize = ImageDraw.Draw(rasterPoly)
                    rasterize.polygon(pixels, 0)
                     # 使用PIL图片转换为Numpy掩膜数组
                    mask = image2Array(rasterPoly)####????????????????????????????????????????????????????????????????
                else:
                     rasterPoly = Image.new("L", (pxWidth, pxHeight), 0)
                     # 使用PIL创建一个空白图片用于绘制多边形
                     rasterize = ImageDraw.Draw(rasterPoly)
                     rasterize.polygon(pixels, 1)
                     # 使用PIL图片转换为Numpy掩膜数组
                     mask = image2Array(rasterPoly)####????????????????????????????????????????????????????????????????
                mask_part += mask
            MASK *= mask_part
        # 根据掩膜图层对图像进行裁剪
        #for i in recds:################################################################3
    clip = gdal_array.numpy.choose(MASK, (clip, 0),mode='clip').astype(gdal_array.numpy.float32)
        #保存为tiff文件
        #for i in recds:###################################################################
    gtiffDriver = gdal.GetDriverByName('GTiff')
    if gtiffDriver is None:
        raise ValueError("Can't find GeoTiff Driver")
        #for i in recds:######################################################################
    gtiffDriver.CreateCopy("{}.tif".format(output), OpenArray(clip, prototype_ds=raster, xoff=xoffset, yoff=yoffset))

if __name__ == "__main__":
    main()