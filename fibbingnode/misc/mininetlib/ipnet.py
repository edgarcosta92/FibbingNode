import sys
import math
import json


from ipaddress import ip_interface, ip_network

from mininet.net import Mininet
from mininet.node import Host, OVSKernelSwitch
from mininet.nodelib import LinuxBridge

import fibbingnode.misc.mininetlib as _lib
from fibbingnode.misc.mininetlib import get_logger, PRIVATE_IP_KEY,\
                                        otherIntf, FIBBING_MIN_COST,\
                                        BDOMAIN_KEY, routers_in_bd,\
                                        FIBBING_DEFAULT_AREA
from fibbingnode.misc.mininetlib.iprouter import IPRouter



from fibbingnode.misc.utils import cmp_prefixlen, is_container

log = get_logger()


def isBroadcastDomainBoundary(node):
    return isinstance(node, Host) or isinstance(node, IPRouter)


class IPNet(Mininet):
    """:param private_ip_count: The number of private address per router
                            interface
        :param private_ip_net: The network used for private addresses
        :param private_ip_bindings: The file name for the private ip binding
        :param controller_net: The prefix to use for the Fibbing controllers
                                Internal networks
        :param max_alloc_prefixlen: The maximal prefix for the auto-allocated
                                    broadcast domains
    """
    def __init__(self,
                 router=IPRouter,
                 ipBase='10.0.0.0/8',
                 max_alloc_prefixlen=24,
                 debug=_lib.DEBUG_FLAG,
                 switch=OVSKernelSwitch,
                 *args, **kwargs):
        _lib.DEBUG_FLAG = debug
        if debug:
            log.setLogLevel('debug')
        self.router = router
        self.routers = []
        self.ip_allocs = {}
        self.max_alloc_prefixlen = max_alloc_prefixlen
        self.unallocated_ip_base = [ipBase]
        super(IPNet, self).__init__(ipBase=ipBase,
                                    switch=switch, *args, **kwargs)
        

    def addRouter(self, name, cls=None, **params):
        # self.private_ip_net = "192.0.0.0/8"
        # defaults = {'private_net': self.private_ip_net}
        # defaults.update(params)
        # defaults = params
        # print name, defaults
        if not cls:
            cls = self.router
        #print cls
        print params
        r = cls(name, **params)
        #print self.routers
        #print "addes the object routers into some list, I guess used afterwords for the configuration"
        self.routers.append(r)
        self.nameToNode[name] = r
        #print self.nameToNode
        return r


    def __iter__(self):
        for r in self.routers:
            yield r.name
        for n in super(IPNet, self).__iter__():
            yield n

    def __len__(self):
        return len(self.routers) + super(IPNet, self).__len__()

    def buildFromTopo(self, topo=None):
        log.info('\n*** Adding Routers:\n')
        
        for routerName in topo.routers():
            #adds routers, I guess that time it does create the "hosts"
            self.addRouter(routerName, **topo.nodeInfo(routerName))
            log.info(routerName + ' ')
        # log.info('\n\n*** Adding FibbingControllers:\n')

        #TODO: check this controller thing
        # ctrlrs = topo.controllers()
        self.controller = None
        # if not ctrlrs:
        #     self.controller = None
        # for cName in topo.controllers():
        #     self.addController(cName, **topo.nodeInfo(cName))
        #     log.info(cName + ' ')
        # log.info('\n')
        super(IPNet, self).buildFromTopo(topo)

    def start(self):
        for n in self.values():
            for i in n.intfList():
                self.ip_allocs[str(i.ip)] = n
                # try:
                #     for sec in i.params[PRIVATE_IP_KEY]:
                #         self.ip_allocs[str(sec)] = n
                # except KeyError:
                #     pass
        log.info('*** Starting %s routers\n' % len(self.routers))
        for router in self.routers:
            log.info(router.name + ' ')
            #check that and modify what quagga does, just remove private things
            router.start()
        log.info('\n')
        #puts to all the hosts its default gateway
        log.info('*** Setting default host routes\n')
        for h in self.hosts:
            if 'defaultRoute' in h.params:
                continue  # Skipping hosts with explicit default route
            routers = []
            for itf in h.intfList():
                if itf.name == 'lo':
                    continue
                routers.extend(routers_in_bd(itf.params.get(BDOMAIN_KEY, ())))
            if routers:
                log.info('%s via %s, ' % (h.name, routers[0].node.name))
                h.setDefaultRoute('via %s' % routers[0].ip)
            else:
                log.info('%s is not connected to a router, ' % h.name)
        log.info('\n')
        super(IPNet, self).start()

    def stop(self):
        log.info('*** Stopping %i routers\n' % len(self.routers))
        for router in self.routers:
            log.info(router.name + ' ')
            router.terminate()
        log.info('\n')
        super(IPNet, self).stop()

    def build(self):

        super(IPNet, self).build()
        #At that point all the links and ip in the hosts are set.
        # however now is the moment in which we should set the ips again

        # #TO ERASE
        # for h in self.hosts:
        #      h.cmdPrint("ifconfig")
        #      h.cmdPrint("route -n")
        #
        # for r in self.routers:
        #     r.cmdPrint("ifconfig")
        # ###

        #here it gets all the network domains and its interfaces, amazing!!
        domains = self.broadcast_domains()


        log.info("*** Found", len(domains), "broadcast domains\n")

        self.allocate_primaryIPS(domains)


    def allocate_primaryIPS(self, domains):
        log.info("*** Allocating primary IPs\n")
        for net, domain in self.network_for_domains(self.unallocated_ip_base,
                                                    domains,
                                                    max_prefixlen=self
                                                    .max_alloc_prefixlen):

            hosts = net.hosts()
            for intf in domain:
                ip = str(next(hosts))
                intf.setIP(ip, prefixLen=net.prefixlen)


    @staticmethod
    def network_for_domains(net, domains, scale_factor=1,
                            max_prefixlen=sys.maxint):
        """"Return [ ( subnet, [ intf* ] )* ]
        Assign a network prefix to every broadcast domain
        :param net: the original network to split, if this is a list, modifies
                    it to contain the list of prefixes still free
        :param domains: the list of broadcast domains
        :param scale_factor: the number of ip to assign per interface
        :param max_prefixlen: The maximal length of the prefix allocated for
                              each broadcast domain"""
        domains.sort(key=len, reverse=True)
        # We want to support allocation across multiple network prefixes
        # ip_network(ip_network(x)) is safe -- tests/test_pyaddress.py
        if not is_container(net):
            net = [ip_network(net)]
        else:
            for i, n in enumerate(net):
                net[i] = ip_network(n)
        networks = net
        # Hopefully we only allocate across prefixes in the same IP version...
        net_space = networks[0].max_prefixlen
        """We keep the networks sorted as x < y so that the bigger domains
        take the smallest network before subdividing
        The assumption is that if the domains range from the biggest to
        the smallest, and if the networks are sorted from the smallest
        to the biggest, the biggest domains will take the first network that
        is able to contain it, and split it in several subnets until it is
        restricted to its prefix.
        The next domain then is necessarily of the same size
        (reuses on of the split networks) or smaller:
        use and earlier network or split a bigger one.
        """
        # Need to setup invariant
        networks.sort(cmp=cmp_prefixlen)
        for d in domains:
            if not networks:
                log.error("No subnet left in the prefix space for all"
                          "broadcast domains")
                sys.exit(1)
            intf_count = len(d) * scale_factor
            plen = min(max_prefixlen,
                       net_space - math.ceil(math.log(2 + intf_count, 2)))
            if plen < networks[-1].prefixlen:
                raise ValueError('Could not find a subnet big enough for a '
                                 'broadcast domain, aborting!')
            log.debug('Allocating prefix %s in network %s for interfaces %s',
                      plen, net, d)
            # Try to find a suitable subnet in the list
            for i, net in enumerate(networks):
                nets = []
                # if the subnet is too big for the prefix, expand it
                while plen > net.prefixlen:
                    # Get list of subnets and append to list of previous
                    # subnets as it is bigger wrt. prefixlen
                    nets.extend(net.subnets(prefixlen_diff=1))
                    net = nets.pop(-1)
                # Check if we have an appropriately-sized subnet
                if plen == net.prefixlen:
                    # Remove and return the expanded/used network
                    yield (net, d)
                    del networks[i]
                    # Insert the creadted subnets if any
                    networks.extend(nets)
                    # Sort the array again
                    networks.sort(cmp=cmp_prefixlen)
                    break
                # Otherwise try the next network

    def broadcast_domains(self):
        """Returns [ [ intf ]* ]"""
        domains = []

        itfs = (intf for n in self.values() for intf in n.intfList()
                if intf.name != 'lo' and
                isBroadcastDomainBoundary(intf.node))
        interfaces = {itf: False for itf in itfs}
        for intf, explored in interfaces.iteritems():
            # the interface already belongs to a broadcast domain
            if explored:
                continue
            # create a new domain
            bd = list()
            to_explore = [intf]
            while to_explore:
                # Explore one element
                i = to_explore.pop()
                if isBroadcastDomainBoundary(i.node):
                    bd.append(i)
                    if i in interfaces:
                        interfaces[i] = True
                # check its corresponding interface
                other = otherIntf(i)
                if isBroadcastDomainBoundary(other.node):
                    bd.append(other)
                    if other in interfaces:
                        interfaces[other] = True
                else:
                    # explode the node's interface to explore them
                    to_explore.extend([x for x in other.node.intfList()
                                       if x is not other and x.name != 'lo'])
            domains.append(bd)
            for i in bd:
                i.params[BDOMAIN_KEY] = bd
        return domains

    #TODO: change the fibbing cost to 1? what the fuck is that?
    def addLink(self, node1, node2, port1=None, port2=None,
                cost=FIBBING_MIN_COST, area=FIBBING_DEFAULT_AREA, **params):
        params1 = params.get('params1', {})
        if 'cost' not in params1:
            params1.update(cost=cost)
        params2 = params.get('params2', {})
        if 'cost' not in params2:
            params2.update(cost=cost)
        params1['area'] = area
        params2['area'] = area
        params.update(params1=params1)
        params.update(params2=params2)
        super(IPNet, self).addLink(node1, node2, port1, port2, **params)

    def node_for_ip(self, ip):
        return self.ip_allocs[ip]


class TopologyDB(object):
    """A convenience store for auto-allocated mininet properties.
    This is *NOT* to be used as IGP graph for a controller application,
    use the graphs reported by the southbound controller instead."""
    def __init__(self, db=None, net=None, *args, **kwargs):
        super(TopologyDB, self).__init__(*args, **kwargs)
        """
        dict keyed by node name ->
            dict keyed by - properties -> val
                          - neighbor   -> interface properties
        """
        self.network = {}
        if db:
            self.load(db)
        if net:
            self.parse_net(net)

    def load(self, fpath):
        """Load a topology database from the given filename"""
        with open(fpath, 'r') as f:
            self.network = json.load(f)

    def save(self, fpath):
        """Save the topology database to the given filename"""
        with open(fpath, 'w') as f:
            json.dump(self.network, f)

    def _interface(self, x, y):
        return self.network[x][y]

    def interface(self, x, y):
        """Return the ip_interface for node x facing node y"""
        return ip_interface(self._interface(x, y)['ip'])

    def interface_bandwidth(self, x, y):
        """Return the bandwidth capacity of the interface on node x
        facing node y. If it is unlimited, return -1"""
        return self._interface(x, y)['bw']

    def subnet(self, x, y):
        """Return the subnet linking node x and y"""
        return self.interface(x, y).network.with_prefixlen

    def routerid(self, x):
        """Return the OSPF router id for node named x"""
        n = self.network[x]
        if n['type'] != 'router':
            raise TypeError('%s is not a router' % x)
        return n['routerid']

    def parse_net(self, net):
        """Stores the content of the given network"""
        for h in net.hosts:
            self.add_host(h)
        for s in net.switches:
            self.add_switch(s)
        for r in net.routers:
            self.add_router(r)
        for c in net.controllers:
            self.add_controller(c)

    def _add_node(self, n, props):
        """Register a network node"""
        for itf in n.intfList():
            nh = otherIntf(itf)
            if not nh:
                continue  # Skip loopback and the likes
            props[nh.node.name] = {
                'ip': '%s/%s' % (itf.ip, itf.prefixLen),
                'name': itf.name,
                'bw': itf.params.get('bw', -1)
            }
        self.network[n.name] = props

    def add_host(self, n):
        """Register an host"""
        self._add_node(n, {'type': 'host'})

    def add_controller(self, n):
        """Register an controller"""
        self._add_node(n, {'type': 'controller'})

    def add_switch(self, n):
        """Register an switch"""
        self._add_node(n, {'type': 'switch'})

    def add_router(self, n):
        """Register an router"""
        self._add_node(n, {'type': 'router',
                           'routerid': n.id})
