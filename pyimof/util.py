"""Common tools to optical flow algorithms

"""

import pylab as P
import numpy as np
from scipy import ndimage as ndi
import skimage
from skimage.transform import pyramid_reduce, resize
from skimage.color import hsv2rgb


def forward_diff(p):
    """Forward difference scheme

    """
    p_x = p.copy()
    p_x[:, :-1] -= p[:, 1:]
    p_x[:, -1] = p_x[:, -2]

    p_y = p.copy()
    p_y[:-1, :] -= p[1:, :]
    p_y[-1, :] = p_y[-2, :]

    return p_x, p_y


def div(p1, p2):
    """Divergence of P=(p1, p2) using backward differece scheme.

    """
    p1_x = p1.copy()
    p1_x[:, 1:] -= p1[:, :-1]
    p1_x[:, 0] = p1_x[:, 1]

    p2_y = p2.copy()
    p2_y[1:, :] -= p2[:-1, :]
    p2_y[0, :] = p2_y[1, :]

    return p1_x + p2_y


def warp(I, u, v, x=None, y=None, mode='nearest'):
    """Image warping using the motion field (u, v)

    """
    if (x is None) or (y is None):
        nl, nc = I.shape
        y, x = np.meshgrid(np.arange(nl)-0.5, np.arange(nc)-0.5, indexing='ij')

    return ndi.map_coordinates(I, [y+v, x+u], order=1, mode=mode)


def upscale_flow(u, v, shape):
    """Rescale the values of the vector field (u, v) to the desired shape

    """

    nl, nc = u.shape
    sy, sx = shape[0]/nl, shape[1]/nc

    u = resize(u, shape, order=0, preserve_range=True,
               anti_aliasing=False)
    v = resize(v, shape, order=0, preserve_range=True,
               anti_aliasing=False)

    return sx*u, sy*v


def get_pyramid(I0, I1, downscale=2.0, min_size=16):
    """Image pyramid construction

    """

    if I0.shape != I1.shape:
        raise ValueError("Images should have the same size")

    pyramid = [(I0, I1)]
    size = min(I0.shape[:2])

    while size > min_size:
        J0 = pyramid_reduce(pyramid[-1][0], downscale, multichannel=False)
        J1 = pyramid_reduce(pyramid[-1][1], downscale, multichannel=False)
        pyramid.append((J0, J1))
        size = min(J0.shape[:2])

    return pyramid[::-1]


def coarse_to_fine(I0, I1, solver, downscale=2.0):
    """Generic coarse to fine solver

    """

    if (I0.ndim != 2) or (I1.ndim != 2):
        raise ValueError("Images should be grayscale.")

    pyramid = get_pyramid(skimage.img_as_float32(I0),
                          skimage.img_as_float32(I1), downscale)

    u = np.zeros_like(pyramid[0][0])
    v = np.zeros_like(u)

    u, v = solver(pyramid[0][0], pyramid[0][1], u, v)

    for J0, J1 in pyramid[1:]:
        u, v = upscale_flow(u, v, J0.shape)
        u, v = solver(J0, J1, u, v)

    return u, v


def flow_to_color(u, v, thresh=1e9, maxflow=None):
    """Color code the vector field (u, v).

    """
    np.nan_to_num(u)
    np.nan_to_num(v)
    idx = np.logical_or(abs(u) > thresh, abs(v) > thresh)
    u[idx] = 0
    v[idx] = 0
    N = np.sqrt(u*u + v*v)
    maxN = N.max()

    if (maxflow is not None) and (maxflow > 0):
        maxN = maxflow

    maxN += 1e-12

    u /= maxN
    v /= maxN
    N /= maxN

    hsv = np.concatenate([np.atleast_3d(v),
                          np.atleast_3d(u),
                          np.atleast_3d(N)], -1)

    return hsv2rgb(hsv)


def flow_to_mdlburry_color(u, v, thresh=1e9, maxflow=None):
    """Color code the vector field (u, v).

    """

    # Preprocess flow
    nanIdx = np.logical_or(np.isnan(u), np.isnan(v))
    u[nanIdx] = 0
    v[nanIdx] = 0

    idx = np.logical_or(abs(u) > thresh, abs(v) > thresh)
    u[idx] = 0
    v[idx] = 0

    N = np.sqrt(u*u + v*v)
    maxN = N.max()

    if (maxflow is not None) and (maxflow > 0):
        maxN = maxflow

    maxN += 1e-12

    u /= maxN
    v /= maxN

    # generate colors

    col_range = [0, 15, 6, 4, 11, 13, 6]
    ncol = np.sum(col_range)

    _, RY, YG, GC, CB, BM, MR = col_range

    colorWheel = np.zeros((ncol, 3))
    col = 0

    colorWheel[:RY, 0] = 255
    colorWheel[:RY, 1] = np.floor(255*np.arange(RY)/RY)
    col += RY

    colorWheel[col:col+YG, 0] = 255 - np.floor(255*np.arange(YG)/YG)
    colorWheel[col:col+YG, 1] = 255
    col += YG

    colorWheel[col:col+GC, 1] = 255
    colorWheel[col:col+GC, 2] = np.floor(255*np.arange(GC)/GC)
    col += GC

    colorWheel[col:col+CB, 1] = 255 - np.floor(255*np.arange(CB)/CB)
    colorWheel[col:col+CB, 2] = 255
    col += CB

    colorWheel[col:col+BM, 2] = 255
    colorWheel[col:col+BM, 0] = np.floor(255*np.arange(BM)/BM)
    col += BM

    colorWheel[col:col+MR, 2] = 255 - np.floor(255*np.arange(MR)/MR)
    colorWheel[col:col+MR, 0] = 255

    a = np.arctan2(-v, -u)/np.pi
    fk = (a+1)/2 *(ncol-1)

    k0 = np.int32(fk)
    k1 = k0+1
    k1[k1 == ncol] = 0

    f = fk-k0

    idx = N <= 1

    nl, nc = u.shape
    img = np.empty((nl, nc, 3), dtype=np.uint8)
    for i in range(3):
        tmp = colorWheel[:, i]
        col0 = tmp[k0]/255
        col1 = tmp[k1]/255
        col = (1-f)*col0 + f*col1
        col[idx] = 1-N[idx]*(1-col[idx])

        col[~idx] *= 0.75
        img[..., i] = np.uint8(255*col*(1-nanIdx))

    return img/255
