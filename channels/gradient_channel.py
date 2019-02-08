import numpy as np
from numpy.fft import fftn, ifftn
from ..base import Channel
from ..utils.conv_filters import gradient_filters
import logging


class GradientChannel(Channel):
    "Gradient channel x = grad z "

    def __init__(self, shape, real=True):
        self.d = len(shape)
        self.shape = shape
        self.real = real
        self.repr_init()
        self.filter = gradient_filters(shape)
        self.axes = list(range(1, self.d + 1)) # axes over which fft is taken
        # conv weights = time reversed filter; their ffts are conjugate
        self.w_fft_bar = fftn(self.filter, axes=self.axes)
        self.w_fft = np.conjugate(self.w_fft_bar)
        self.spectrum = (np.absolute(self.w_fft)**2).sum(axis=0)
        assert self.spectrum.shape == shape

    def convolve(self, z):
        if (z.shape != self.shape):
            raise ValueError(f"Bad shape for z: {z.shape} expected {self.shape}")
        z_fft = fftn(z)
        x_fft = self.w_fft * z_fft[np.newaxis,:]
        x = ifftn(x_fft, axes=self.axes) # no fft over axis=0 (grad direction)
        if self.real:
            x = np.real(x)
        return x

    def sample(self, Z):
        return self.convolve(Z)

    def math(self):
        return r"$\nabla$"

    def second_moment(self, tau):
        return tau * self.spectrum.mean() / self.d

    def compute_n_eff(self, az, ax):
        "Effective number of parameters = overlap in z"
        if ax == 0:
            logging.info(f"ax=0 in {self} compute_n_eff")
            return 0.
        if az / ax == 0:
            logging.info(f"az/ax=0 in {self} compute_n_eff")
            return 1.
        n_eff = np.mean(self.spectrum / (az / ax + self.spectrum))
        return n_eff

    def compute_backward_mean(self, az, bz, ax, bx, return_fft=False):
        # estimate z from x = Wz
        bx_fft = fftn(bx, axes=self.axes) # no fft over axis=0 (grad direction)
        bz_fft = fftn(bz)
        resolvent = 1 / (az + ax * self.spectrum)
        rz_fft = resolvent * (bz_fft + (self.w_fft_bar * bx_fft).sum(axis=0))
        if return_fft:
            return rz_fft
        rz = ifftn(rz_fft)
        if self.real:
            rz = np.real(rz)
        return rz

    def compute_forward_mean(self, az, bz, ax, bx):
        # estimate x from x = Wz we have rx = W rz
        rz_fft = self.compute_backward_mean(az, bz, ax, bx, return_fft=True)
        rx_fft = self.w_fft * rz_fft[np.newaxis,:]
        rx = ifftn(rx_fft, axes=self.axes)
        if self.real:
            rx = np.real(rx)
        return rx

    def compute_backward_variance(self, az, ax):
        if az == 0:
            logging.info(f"az=0 in {self} compute_backward_variance")
            i_mean = np.mean(1 / self.spectrum)
            return i_mean / ax
        n_eff = self.compute_n_eff(az, ax)
        vz = (1 - n_eff) / az
        return vz

    def compute_forward_variance(self, az, ax):
        if ax == 0:
            logging.info(f"ax=0 in {self} compute_forward_variance")
            s_mean = np.mean(self.spectrum)
            return s_mean / az
        n_eff = self.compute_n_eff(az, ax)
        vx = n_eff / (ax * self.d)
        return vx

    def compute_backward_posterior(self, az, bz, ax, bx):
        # estimate z from x = Wz
        rz = self.compute_backward_mean(az, bz, ax, bx)
        vz = self.compute_backward_variance(az, ax)
        return rz, vz

    def compute_forward_posterior(self, az, bz, ax, bx):
        # estimate x from x = Wz
        rx = self.compute_forward_mean(az, bz, ax, bx)
        vx = self.compute_forward_variance(az, ax)
        return rx, vx

    def compute_backward_error(self, az, ax, tau):
        vz = self.compute_backward_variance(az, ax)
        return vz

    def compute_forward_error(self, az, ax, tau):
        vx = self.compute_forward_variance(az, ax)
        return vx
