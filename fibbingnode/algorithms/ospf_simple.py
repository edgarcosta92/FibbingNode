import utils as ssu
import networkx as nx
from fibbingnode import log
from fibbingnode.misc.igp_graph import ShortestPath


class OSPFSimple(object):
    def __init__(self):
        self.new_edge_metric = 10e4

    def get_fake_lsas(self):
        return self.fake_ospf_lsas

    def nhs_for(self, node, dag, dest):
        req_nhs = dag.successors(node)
        # compute the originals next-hops of the current node
        try:
            original_nhs = [p[1]
                            for p in self.igp_paths.default_path(node, dest)]
        except KeyError:
            original_nhs = []
        return req_nhs, original_nhs

    @staticmethod
    def require_fake_node(req_nhs, original_nhs):
        return len(req_nhs) > 1 or\
               len(original_nhs) > 1 or\
               set(req_nhs).symmetric_difference(original_nhs)

    def solve(self, topo, requirement_dags):
        # a list of tuples with info on the node to be attracted,
        # the forwarding address, the cost to be set in the fake LSA,
        # and the respective destinations
        self.fake_ospf_lsas = []
        self.reqs = requirement_dags
        self.igp_graph = topo
        self.igp_paths = ShortestPath(self.igp_graph)
        log.debug('Original SPT: %s', self.igp_paths)
        # process input forwarding DAGs, one at the time
        for dest, dag in requirement_dags.iteritems():
            log.debug('Solving DAG for dest %s', dest)
            self.dest, self.dag = dest, dag
            log.debug('Checking dest in dag')
            ssu.add_dest_to_graph(dest, dag)
            log.debug('Checking dest in igp graph')
            ssu.add_dest_to_graph(dest, topo,
                                  edges_src=dag.predecessors,
                                  spt=self.igp_paths,
                                  metric=self.new_edge_metric)
            ssu.complete_dag(dag, topo, dest, self.igp_paths,
                             skip=self.reqs.keys())
            # Add temporarily the destination to the igp graph and/or req dags
            if not ssu.solvable(dag, topo):
                log.warning('Skipping requirement for dest: %s', dest)
                continue
            for node in nx.topological_sort(dag, reverse=True)[1:]:
                nhs, original_nhs = self.nhs_for(node, dag, dest)
                if not self.require_fake_node(nhs, original_nhs):
                    log.debug('%s does not require a fake node (%s - %s)',
                              node, nhs, original_nhs)
                    continue
                for req_nh in nhs:
                    log.debug('Placing a fake node for nh %s', req_nh)
                    self.fake_ospf_lsas.append(ssu.LSA(node=node,
                                                       nh=req_nh,
                                                       cost=-1,
                                                       dest=dest))
        return self.fake_ospf_lsas
