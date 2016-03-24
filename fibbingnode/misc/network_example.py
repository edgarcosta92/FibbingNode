import argparse

import fibbingnode.misc.mininetlib as _lib
from fibbingnode.misc.mininetlib.cli import FibbingCLI
from fibbingnode.misc.mininetlib.ipnet import IPNet, TopologyDB
from fibbingnode.misc.mininetlib.iptopo import IPTopo

from mininet.nodelib import LinuxBridge



from mininet.util import custom
from mininet.link import TCIntf
#from mininet.cli import CLI

DB_path = '/tmp/db.topo'

S1 = 's1'
R0 = 'r0'
R1 = 'r1'
R2 = 'r2'
R3 = 'r3'
R4 = 'r4'
D1 = 'd1'


class FatTree(IPTopo):

    def __init__(self, k=4,extraSwitch=True, *args, **kwargs):
        #k must be multiple of 2
        self.k = k
        self.extraSwitch = extraSwitch
        super(FatTree,self).__init__(*args,**kwargs)




    def build(self, *args, **kwargs):

        #build the topology

        aggregationRouters = self.addPods(self.extraSwitch)
        coreRouters = self.addCoreRouters()
        self.connectCoreAggregation(aggregationRouters, coreRouters)


    def connectCoreAggregation(self,aggregationRouters, coreRouters):


        #connect every aggregation router with k/2 core routers
        for i, aggregationRouter in enumerate(aggregationRouters):

            #position inside the pod
            position = i % (self.k/2)

            #connect with core routers
            for coreRouter in coreRouters[(position*(self.k/2)):((position+1)*(self.k/2))]:
                self.addLink(aggregationRouter,coreRouter)



    def addOVSHost(self, podNum, index):
        """
        Creates a host/switch pair. Every host in the fat tree topology is based on a
        normal mininet host + an ovs switch that allows flow modifications.
        :param index: Host number in the topology
        :return:returns a tuple of the form (h, sw)
        """

        h = self.addHost("h_%d_%d" % (podNum,index))
        sw = self.addSwitch("ovs_%d_%d" % (podNum,index))

        self.addLink(h,sw)

        return {"host":h,"ovs":sw}


    def addHostsGrup(self,podNum, startIndex, extraSwitch=True):

        """

        :param podNum:
        :param startIndex:
        :param extraSwitch:
        :return:
        """

        # Contains the name of the switches. They will be used to connect the hosts to the higher layers
        switches = []

        if extraSwitch:

            #First a switch to grup all the hosts is created
            switch_index = startIndex/self.k
            sw = self.addSwitch("sw_%d_%d" % (podNum, switch_index))

            #creatres k/2 OVSHosts
            for i in range(self.k/2):
                ovsHosts = self.addOVSHost(podNum, startIndex+i)
                #add link between the ovs switch and the normal switch
                self.addLink(ovsHosts["ovs"], sw)
            #we add sw in switches list. Switches list is used as a return value,
            #  and will be used later to know what needs to be connected with the edge router
            switches.append(sw)

        #case in which all the hosts are directly connected to the edge router
        else:
            for i in range(self.k/2):
                ovsHosts = self.addOVSHost(podNum, startIndex+i)
                switches.append(ovsHosts["ovs"])

        return switches

    def addPods(self,extraSwitch=True):

        aggregationRouters = []

        #add k pods and store the aggregation Routers in aggregationRouters
        for i in range(self.k):
            aggregationRouters += (self.addPod(i, extraSwitch))

        return aggregationRouters

    def addPod(self,podNum,extraSwitch=True):

        """

        :param podNum:
        :param extraSwitch:
        :return:
        """

        edgeRouters = []
        aggregationRouters = []

        #Add Aggregation and Edge routers
        for i in range(self.k/2):
            edgeRouters.append(self.addRouter("r_%d_e%d" % (podNum, i)))
            aggregationRouters.append(self.addRouter("r_%d_a%d" % (podNum, i)))

        #Connect Aggregation layer with Edge layer
        for edge_router in edgeRouters:
            for aggregation_router in aggregationRouters:
                self.addLink(edge_router, aggregation_router)

        #add hosts to the edge layer, each edge router should be connected to k/2 hosts
        startIndex  = 0
        for edge_router in edgeRouters:
            #create hosts and switches
            switches = self.addHostsGrup(podNum, startIndex, extraSwitch)

            #connect switch/switches with edge router
            for switch in switches:
                self.addLink(edge_router, switch)

            startIndex += len(switches)

        #only aggregation Routers are needed to connect with the core layer
        return aggregationRouters


    def addCoreRouters(self):

        """

        :return:
        """

        coreRouters = []

        #create (k/2)^2 core routers. Each one will be connected to every pod through one aggregation router
        for i in range((self.k/2)**2):
            coreRouters.append(self.addRouter("r_c%d" % i))

        return coreRouters


class TestTopo(IPTopo):


    def __init__(self, k=4,*args, **kwargs):
        self.k = k
        super(TestTopo,self).__init__(*args,**kwargs)

    def build(self,*args, **kwargs):



        s1 = self.addHost(S1)
        d1 = self.addHost(D1)

        s2 = self.addHost("s2")

        sw0 = self.addSwitch("sw0")

        r0 = self.addRouter(R0)
        r1 = self.addRouter(R1)
        r2 = self.addRouter(R2)
        r3 = self.addRouter(R3)
        r4 = self.addRouter(R4)

        
        #Links from hosts to routers        
        self.addLink(s1, sw0)
        self.addLink(r4, d1)
        self.addLink(s2, sw0)
        self.addLink(sw0,r0)


        #Links between routers
        self.addLink(r0,r1)
        self.addLink(r0,r1)
        self.addLink(r0,r1)
        self.addLink(r0,r1)

        self.addLink(r1,r2)
        self.addLink(r1,r2)
        self.addLink(r1,r2)
        self.addLink(r1,r2)

        self.addLink(r2,r3)
        self.addLink(r2,r3)
        self.addLink(r2,r3)
        self.addLink(r2,r3)

        self.addLink(r3,r4)
        self.addLink(r3,r4)
        self.addLink(r3,r4)
        self.addLink(r3,r4)


    

def launch_network():

    #topo = TestTopo()
    topo = FatTree(k =2, extraSwitch=True)
    intf = custom(TCIntf)

    #creates nodes and links
    net = IPNet(topo=topo,
                debug=_lib.DEBUG_FLAG,
                intf=intf, switch=LinuxBridge)

    #just stores the topology in a json object, it does not take into account mulipaths between nodes
    TopologyDB(net=net).save(DB_path)
    
    #start processes(quagga) and maps again the ips
    net.start()


    FibbingCLI(net)
    net.stop()


if __name__ == '__main__':


    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()

    group.add_argument('-n', '--net',
                       help='Start the Mininet topology',
                       action='store_true',
                       default=True)
    parser.add_argument('-d', '--debug',
                        help='Set log levels to debug',
                        action='store_true',
                        default=False)
    args = parser.parse_args()
    if args.debug:
        _lib.DEBUG_FLAG = True
        from mininet.log import lg
        from fibbingnode import log
        import logging
        log.setLevel(logging.DEBUG)
        lg.setLogLevel('debug')
    if args.net:
        launch_network()
