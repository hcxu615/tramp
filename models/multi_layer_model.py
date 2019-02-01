from ..base import Prior, Channel, Likelihood
from .factor_model import FactorModel
import networkx as nx


def check_layers(layers):
    if not isinstance(layers[0], Prior):
        raise ValueError("first layer must be a Prior")
    for i, layer in enumerate(layers[1:-1]):
        if not isinstance(layer, Channel):
            raise ValueError(f"intermediate layer i={i} must be a Channel")
    if isinstance(layers[-1], Channel):
        if layers[-1].n_next != 1:
            raise ValueError("last layer must be a Channel with one output")
    elif not isinstance(layers[-1], Likelihood):
        raise ValueError("last layer must be a Channel or a Likelihood")


class MultiLayerModel(FactorModel):
    def __init__(self, layers):
        check_layers(layers)
        self.observed = isinstance(layers[-1], Likelihood)
        self.layers = layers
        factor_dag = self._build_factor_dag(layers)
        FactorModel.__init__(self, factor_dag)

    def __repr__(self):
        pad = "  "
        padded = "\n".join([
            f"{pad}{layer}," for layer in self.layers
        ])
        inner = f"\n{padded}\n{pad}observed={self.observed}\n"
        return f"MultiLayer({inner})"

    def _build_factor_dag(self, layers):
        # factor_dag = layers[0] @ ... @ layers[n-1]
        factor_dag = layers[0]
        for layer in layers[1:]:
            factor_dag = factor_dag @ layer
        factor_dag = factor_dag.to_factor_dag()
        return factor_dag
