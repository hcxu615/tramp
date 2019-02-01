import numpy as np
import networkx as nx
import logging
from ..base import Variable, Factor
from ..models import DAGModel
from .initial_conditions import ConstantInit
from .callbacks import PassCallback

def find_variable_in_nodes(id, nodes):
    matchs = [
        node for node in nodes
        if isinstance(node, Variable) and node.id == id
    ]
    assert len(matchs)==1
    return matchs[0]

class MessagePassing():
    _default_initializer = ConstantInit(a=0, b=0)
    _default_callback = PassCallback()

    def __init__(self, model, message_keys, forward, backward, update):
        if not isinstance(model, DAGModel):
            raise ValueError(f"model {model} is not a DAGModel")
        model.init_shapes()
        model.second_moment()
        self.message_keys = message_keys
        self.forward = forward
        self.backward = backward
        self.update = update
        self.model_dag = model.dag
        self.forward_ordering = model.forward_ordering
        self.backward_ordering = model.backward_ordering
        self.variables = model.variables
        self.n_iter = 0

    def init_message_dag(self, initializer):
        message_dag = nx.DiGraph()
        message_dag.add_nodes_from(self.model_dag.nodes(data=True))
        message_dag.add_edges_from(
            self.model_dag.edges(data=True), direction="fwd", n_iter=0
        )
        message_dag.add_edges_from(
            self.model_dag.reverse().edges(data=True), direction="bwd", n_iter=0
        )
        for source, target, data in message_dag.edges(data=True):
            if data["direction"] == "fwd" and isinstance(source, Variable):
                data["tau"] = self.model_dag.node[source]["tau"]
            variable = source if isinstance(source, Variable) else target
            for message_key in self.message_keys:
                shape = self.model_dag.node[variable]["shape"]
                data[message_key] = initializer.init(message_key, shape)
        self.message_dag = message_dag
        nx.freeze(self.message_dag)

    def reset_message_dag(self, message_dag):
        self.message_dag = message_dag
        self.variables = [
            node for node in message_dag.nodes()
            if isinstance(node, Variable)
        ]
        self.factors = [
            node for node in message_dag.nodes()
            if isinstance(node, Factor)
        ]

    def update_message(self, new_message):
        for source, target, new_data in new_message:
            n_iter = self.message_dag[source][target]["n_iter"]
            new_data.update(n_iter=n_iter + 1)
            self.message_dag[source][target].update(new_data)

    def forward_message(self):
        for node in self.forward_ordering:
            message = self.message_dag.in_edges(node, data=True)
            new_message = self.forward(node, message)
            self.update_message(new_message)

    def backward_message(self):
        for node in self.backward_ordering:
            message = self.message_dag.in_edges(node, data=True)
            new_message = self.backward(node, message)
            self.update_message(new_message)

    def update_variables(self):
        for variable in self.variables:
            message = self.message_dag.in_edges(variable, data=True)
            new_data = self.update(variable, message)
            self.message_dag.node[variable].update(new_data)

    def get_variables_data(self):
        variables_data = []
        for variable in self.variables:
            data = dict(id=variable.id, variable=variable)
            data.update(self.message_dag.node[variable])
            variables_data.append(data)
        return variables_data

    def check_any_small(self):
        "Returns True if any v is below epsilon."
        epsilon = 1e-10
        any_small = False
        for variable in self.variables:
            new_v = self.message_dag.node[variable]["v"]
            if new_v < epsilon:
                any_small = True
                logging.info(f"new_v={new_v}<epsilon={epsilon} for {variable}")
        return any_small

    def check_any_nan(self):
        "Returns True if any v is nan."
        any_nan = False
        for variable in self.variables:
            new_v = self.message_dag.node[variable]["v"]
            if np.isnan(new_v):
                any_nan = True
                logging.info(f"new_v is nan for {variable}")
        return any_nan

    def check_any_increasing(self, old_message_dag):
        "Returns True if any v is increasing."
        any_increasing = False
        for variable in self.variables:
            old_variable = find_variable_in_nodes(
                variable.id, old_message_dag.nodes()
            )
            old_v = old_message_dag.node[old_variable]["v"]
            new_v = self.message_dag.node[variable]["v"]
            if new_v > old_v:
                any_increasing = True
                logging.info(f"new_v={new_v}>old_v={old_v} for {variable}")
        return any_increasing

    def iterate(self, max_iter,
                callback=None, initializer=None, warm_start=False,
                check_nan=True, check_decreasing=True):
        initializer = initializer or self._default_initializer
        callback = callback or self._default_callback
        if warm_start:
            if not hasattr(self, "message_dag"):
                raise ValueError("message dag was not initialized")
            logging.info(f"warm start with n_iter={self.n_iter} - no initialization")
        else:
            logging.info(f"init message dag with {initializer}")
            self.n_iter = 0
            self.init_message_dag(initializer)
        for i in range(max_iter):
            # backup message_dag
            if (i>0) and (check_nan or check_decreasing):
                old_message_dag = self.message_dag.copy()
            # forward, backward, update pass
            self.forward_message()
            self.backward_message()
            self.update_variables()
            # early stoppings with restoring message_dag
            if (i>0) and check_nan:
                any_nan = self.check_any_nan()
                if any_nan:
                    logging.warn("nan v: restoring old message dag")
                    self.reset_message_dag(old_message_dag)
                    logging.info(f"terminated after n_iter={self.n_iter} iterations")
                    return
            if (i>0) and check_decreasing:
                any_increasing = self.check_any_increasing(old_message_dag)
                if any_increasing:
                    logging.warn("increasing v: restoring old message dag")
                    self.reset_message_dag(old_message_dag)
                    logging.info(f"terminated after n_iter={self.n_iter} iterations")
                    return
            # callbacks
            self.n_iter += 1
            stop = callback(self, i, max_iter)
            logging.debug(f"n_iter={self.n_iter}")
            if stop:
                logging.info(f"terminated after n_iter={self.n_iter} iterations")
                return
