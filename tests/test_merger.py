#!/usr/bin/env python
# -*- coding: utf-8 -*-
import unittest
import collections
import fibbingnode.algorithms.merger as merger
import fibbingnode.algorithms.utils as ssu
from fibbingnode.misc.igp_graph import IGPGraph
from fibbingnode import log


#
# Useful tip to selectively disable test: @unittest.skip('reason')
#


def check_fwd_dags(fwd_req, topo, lsas, solver):
    correct = True
    topo = topo.copy()
    # Check that the topology/dag contain the destinations, otherwise add it
    for dest, dag in fwd_req.iteritems():
        dest_in_dag = dest in dag
        dest_in_graph = dest in topo
        if not dest_in_dag or not dest_in_graph:
            if not dest_in_dag:
                sinks = ssu.find_sink(dag)
            else:
                sinks = dag.predecessors(dest)
            for s in sinks:
                if not dest_in_dag:
                    dag.add_edge(s, dest)
                if not dest_in_graph:
                    topo.add_edge(s, dest, metric=solver.new_edge_metric)
    fake_nodes = {}
    local_fake_nodes = collections.defaultdict(list)
    f_ids = set()
    for lsa in lsas:
        if lsa.cost > 0:
            f_id = '__f_%s_%s_%s' % (lsa.node, lsa.nh, lsa.dest)
            f_ids.add(f_id)
            fake_nodes[(lsa.node, f_id, lsa.dest)] = lsa.nh
            cost = topo[lsa.node][lsa.nh]['metric']
            topo.add_edge(lsa.node, f_id, metric=cost)
            topo.add_edge(f_id, lsa.dest, metric=lsa.cost - cost)
            log.debug('Added a globally-visible fake node: '
                      '%s - %s - %s - %s - %s [-> %s]',
                      lsa.node, cost, f_id, lsa.cost - cost, lsa.dest, lsa.nh)
        else:
            local_fake_nodes[(lsa.node, lsa.dest)].append(lsa.nh)
            log.debug('Added a locally-visible fake node: %s -> %s',
                      lsa.node, lsa.nh)

    spt = ssu.all_shortest_paths(topo, metric='metric')
    for dest, req_dag in fwd_req.iteritems():
        log.info('Validating requirements for dest %s', dest)
        dag = IGPGraph()
        for n in filter(lambda n: n not in fwd_req, topo):
            if n in f_ids:
                continue
            log.debug('Checking paths of %s', n)
            for p in spt[n][0][dest]:
                log.debug('Reported path: %s', p)
                for u, v in zip(p[:-1], p[1:]):
                    try:  # Are we using a globally-visible fake node?
                        nh = fake_nodes[(u, v, dest)]
                        log.debug('%s uses the globally-visible fake node %s '
                                  'to get to %s', u, v, nh)
                        dag.add_edge(u, nh)  # Replace by correct next-hop
                        break
                    except KeyError:
                            # Are we using a locally-visible one?
                            nh = local_fake_nodes[(u, dest)]
                            if nh:
                                log.debug('%s uses a locally-visible fake node'
                                          ' to get to %s', u, nh)
                                for h in nh:
                                    dag.add_edge(u, h)  # Replace by true nh
                                break
                            else:
                                dag.add_edge(u, v)  # Otherwise follow the SP
        # Now that we have the current fwing dag, compare to the requirements
        for n in req_dag:
            successors = set(dag.successors(n))
            req_succ = set(req_dag.successors(n))
            if successors ^ req_succ:
                log.error('The successor sets for node %s differ, '
                          'REQ: %s, CURRENT: %s', n, req_succ, successors)
                correct = False
            predecessors = set(dag.predecessors(n))
            req_pred = set(req_dag.predecessors(n))
            # Also requires to have a non-null successor sets to take into
            # account the fact that the destination will have new adjacencies
            # through fake nodes
            if predecessors ^ req_pred and successors:
                log.error('The predecessors sets for %s differ, '
                          'REQ: %s, CURRENT: %s', n, req_pred, predecessors)
                correct = False
    if correct:
        log.info('All forwarding requirements are enforced!')
    return correct


class Gadgets():

    def __init__(self):
        self.rocketfuel_dir = "../topologies/weights-dist/"
        self._setUpTrapezoid()
        self._setUpDiamond()
        self._setUpSquare()
        self._setUpPaperGadget()
        self._setUpWeird()
        self._setUpParallelTracks()
        self._setUpDoubleDiamond()

    @staticmethod
    def _add_edge(g, src, dst, metric):
        g.add_edges_from([(src, dst), (dst, src)], metric=metric)

    def _setUpParallelTracks(self):
        #    A2--B2--C2--D2
        #   /|   |   |   |
        #  D-A1--B1--C1--D1
        self.parallel = g = IGPGraph()
        self._add_edge(g, 'D', 'A1', 2)
        self._add_edge(g, 'D', 'A2', 2)
        self._add_edge(g, 'B2', 'A2', 2)
        self._add_edge(g, 'B1', 'A1', 2)
        self._add_edge(g, 'B1', 'C1', 2)
        self._add_edge(g, 'B2', 'C2', 2)
        self._add_edge(g, 'C2', 'D2', 2)
        self._add_edge(g, 'C1', 'D1', 2)
        self._add_edge(g, 'D2', 'D1', 2)
        self._add_edge(g, 'C2', 'C1', 2)
        self._add_edge(g, 'B2', 'B1', 2)
        self._add_edge(g, 'A2', 'A1', 2)

    def _setUpWeird(self):
        #     +-----D-----+
        #    /      |      \
        #   2       2       2
        #  /        |        \
        # A -- 4 -- B -- 2 -- C
        self.weird = g = IGPGraph()
        self._add_edge(g, 'A', 'B', 4)
        self._add_edge(g, 'B', 'C', 2)
        self._add_edge(g, 'D', 'C', 2)
        self._add_edge(g, 'D', 'B', 2)
        self._add_edge(g, 'D', 'A', 2)

    def _setUpPaperGadget(self):
        # H1 -- 19 -- A1 ---------+
        #  |                      |
        #  +-- 10 ----+           2
        #             |           |
        #  H2 -- 2 -- X -- 100 -- Y
        #  |         / \          |
        #  6  H3 -- 2   \         |
        #  |   |        8         |
        #  |   6----+  /         17
        #  |        | /           |
        #  +--------A2------------+
        #
        self.paper_gadget = g = IGPGraph()
        self._add_edge(g, 'H1', 'A1', 19)
        self._add_edge(g, 'H1', 'X', 10)
        self._add_edge(g, 'A1', 'Y', 2)
        self._add_edge(g, 'X', 'Y', 100)
        self._add_edge(g, 'X', 'H2', 2)
        self._add_edge(g, 'X', 'H3', 2)
        self._add_edge(g, 'X', 'A2', 8)
        self._add_edge(g, 'H3', 'A2', 6)
        self._add_edge(g, 'H2', 'A2', 6)
        self._add_edge(g, 'Y', 'A2', 17)

    def _setUpTrapezoid(self):
        #  R1 -- 100 -- E1 -- 10 -+
        #   |                     |
        #  100                    D
        #   |                     |
        #  R2 -- 10  -- E2 -- 10 -+

        self.trap = g = IGPGraph()
        self._add_edge(g, 'R1', 'E1', metric=100)
        self._add_edge(g, 'R1', 'R2', metric=100)
        self._add_edge(g, 'R2', 'E2', metric=10)
        self._add_edge(g, 'E1', 'D', metric=10)
        self._add_edge(g, 'E2', 'D', metric=10)

    def _setUpSquare(self):
        self.square = g = IGPGraph()
        # T1  --10--  T2
        #  |    \       |
        #  10     5    100
        #  |        \   |
        #  B1  --3--   B2  --100--D1
        #  |
        # 100
        #  |
        #  D2
        self._add_edge(g, 'B1', 'B2', metric=3)
        self._add_edge(g, 'T1', 'B1', metric=10)
        self._add_edge(g, 'T2', 'T1', metric=10)
        self._add_edge(g, 'B2', 'T1', metric=5)
        self._add_edge(g, 'T2', 'B2', metric=100)
        self._add_edge(g, 'D1', 'B2', metric=100)
        self._add_edge(g, 'D2', 'B1', metric=100)

    def _setUpDiamond(self):
        #  A  ---5---  Y1
        #  | \         |
        #  | 10        10
        #  |  \        |
        #  |  Y2 -15-- X ---50--- D
        #  |           |          |
        #  25 +--30----+          |
        #  | /                    |
        #  O -------- 10 ---------+
        self.diamond = g = IGPGraph()
        self._add_edge(g, 'A', 'Y1', metric=5)
        self._add_edge(g, 'Y1', 'X', metric=10)
        self._add_edge(g, 'A', 'Y2', metric=10)
        self._add_edge(g, 'Y2', 'X', metric=15)
        self._add_edge(g, 'X', 'D', metric=50)
        self._add_edge(g, 'A', 'O', metric=25)
        self._add_edge(g, 'X', 'O', metric=30)
        self._add_edge(g, 'D', 'O', metric=10)

    def _setUpDoubleDiamond(self):
        #  + --------19--------- +
        #  |                     |
        #  H1 ---10--- Y1        |
        #    \         |         |
        #    15        5         |
        #     \        |         |
        #     Y2 -10-  X --100-- D --1000-- 1/8
        #              |         |
        #     H2---2---+         |
        #     /                  |
        #    6                   |
        #   /                    |
        #  A -------- 17 --------+
        self.ddiamond = g = IGPGraph()
        self._add_edge(g, 'H1', 'D', metric=19)
        self._add_edge(g, 'H1', 'Y1', metric=10)
        self._add_edge(g, 'Y1', 'X', metric=5)
        self._add_edge(g, 'H1', 'Y2', metric=15)
        self._add_edge(g, 'Y2', 'X', metric=10)
        self._add_edge(g, 'A', 'H2', metric=6)
        self._add_edge(g, 'H2', 'X', metric=2)
        self._add_edge(g, 'A', 'D', metric=17)
        self._add_edge(g, 'X', 'D', metric=100)


class MergerTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MergerTestCase, self).__init__(*args, **kwargs)
        self.solver_provider = merger.PartialECMPMerger

    def setUp(self):
        self.gadgets = Gadgets()

    def _test(self, igp_topo, fwd_dags, expected_lsa_count):
        solver = self.solver_provider()
        lsas = solver.solve(igp_topo, fwd_dags)
        self.assertTrue(check_fwd_dags(fwd_dags, igp_topo, lsas, solver))
        self.assertTrue(len(lsas) == expected_lsa_count)

    # @unittest.skip('passing')
    def testTrapezoid(self):
        log.warning('Testing Trapezoid')
        self._test(self.gadgets.trap,
                   {'1_8': IGPGraph([('R1', 'R2'),
                                     ('R2', 'E2'),
                                     ('E2', 'D')])},
                   1)

    # @unittest.skip('passing')
    def testTrapezoidWithEcmp(self):
        log.warning('Testing TrapezoidWithEcmp')
        self._test(self.gadgets.trap,
                   {'2_8': IGPGraph([('R1', 'R2'),
                                     ('R2', 'E2'),
                                     ('E2', 'D'),
                                     # ECMP on E1
                                     ('E1', 'D'),
                                     ('E1', 'R1')])},
                   3)

    # @unittest.skip('passing')
    def testDiamond(self):
        log.warning('Testing Diamond')
        self._test(self.gadgets.diamond,
                   {'3_8': IGPGraph([('A', 'Y1'),
                                     ('A', 'Y2'),
                                     ('Y2', 'X'),
                                     ('Y1', 'X'),
                                     ('X', 'D'),
                                     ('O', 'D')])},
                   2)

    # @unittest.skip('passing')
    def testSquareWithThreeConsecutiveChanges(self):
        log.warning('Testing SquareWithThreeConsecutiveChanges')
        self._test(self.gadgets.square,
                   {'3_8': IGPGraph([('D2', 'B1'),
                                     ('B1', 'T1'),
                                     ('T1', 'T2'),
                                     ('T2', 'B2'),
                                     ('B2', 'D1')])},
                   3)

    # @unittest.skip('passing')
    def testSquareWithThreeConsecutiveChangesAndMultipleRequirements(self):
        log.warning('Testing SquareWithThreeConsecutiveChanges'
                    'AndMultipleRequirements')
        dag = IGPGraph([('D2', 'B1'),
                        ('B1', 'T1'),
                        ('T1', 'T2'),
                        ('T2', 'B2'),
                        ('B2', 'D1')])
        self._test(self.gadgets.square,
                   {'3_8': dag, '8_3': dag.reverse(copy=True)},
                   5)

    # @unittest.skip('passing')
    def testPaperGadget(self):
        log.warning('Testing PaperGadget')
        self._test(self.gadgets.paper_gadget,
                   {'3_8': IGPGraph([('H1', 'X'),
                                     ('H2', 'X'),
                                     ('H3', 'X'),
                                     ('X', 'Y'),
                                     ('A1', 'Y'),
                                     ('A2', 'Y')])},
                   1)

    # @unittest.skip('passing')
    def testWeird(self):
        log.warning('Testing Weird')
        self._test(self.gadgets.weird,
                   {'3_8': IGPGraph([('D', 'C'),
                                     ('C', 'B'),
                                     ('B', 'A')])},
                   2)

    # @unittest.skip('passing')
    def testParallel(self):
        log.warning('Testing Parallel')
        self._test(self.gadgets.parallel,
                   {'3_8': IGPGraph([('A2', 'B2'),
                                     ('B2', 'C2'),
                                     ('C2', 'D2'),
                                     ('D2', 'D1'),
                                     ('D1', 'C1'),
                                     ('C1', 'B1'),
                                     ('B1', 'A1'),
                                     ('A1', 'D')])},
                   4)

    # @unittest.skip('passing')
    def testDoubleDiamond(self):
        log.warning('Testing DoubleDiamond')
        self._test(self.gadgets.ddiamond,
                   {'1_8': IGPGraph([('H1', 'Y1'),
                                     ('H1', 'Y2'),
                                     ('Y1', 'X'),
                                     ('Y2', 'X'),
                                     ('H2', 'X'),
                                     ('X', 'D')])},
                   3)

if __name__ == '__main__':
    unittest.main()
