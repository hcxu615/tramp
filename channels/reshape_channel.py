from ..base import Channel


class ReshapeChannel(Channel):
    """
    Reshape vector into tensor of given shape.

    Notes
    -----
    - length of input vector must be consitent with the output shape.
    """

    def __init__(self, shape):
        self.shape = shape
        self.repr_init()

    def sample(self, Z):
        return Z.reshape(self.shape)

    def math(self):
        return r"$\delta$"

    def second_moment(self, tau):
        return tau

    def compute_forward_message(self, az, bz, ax, bx):
        return az, bz.reshape(self.shape)

    def compute_backward_message(self, az, bz, ax, bx):
        return ax, bx.ravel()

    def compute_forward_state_evolution(self, az, ax, tau):
        return az

    def compute_backward_state_evolution(self, az, ax, tau):
        return ax
