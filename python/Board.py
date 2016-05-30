# ----------------------------------------------------------------------
# Copyright (c) 2016, The Regents of the University of California All
# rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
#     * Neither the name of The Regents of the University of California
#       nor the names of its contributors may be used to endorse or
#       promote products derived from this software without specific
#       prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL REGENTS OF THE
# UNIVERSITY OF CALIFORNIA BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
# OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
# TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE
# USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
# DAMAGE.
# ----------------------------------------------------------------------
# Filename: Board.py
# Version: 0.1 
# Description: Defines the Board object, which contains all of the methods
# necessary to create a custom board for the Altera OpenCL Compiler
# Author: Dustin Richmond

# Import Python Utilities
import xml.etree.ElementTree as ET, math
from collections import defaultdict, Counter
# Import Tinker Objects
import Memory, Tinker

class Board():
    def __init__(self, xml):
        Tinker.check_path(xml)
        self.types = {}
        self.info = self.parse_info(ET.parse(xml)) 

    def get_info(self):
        return self.info;

    def print_info(self,l):
        print l*"\t" + "Available Memories: " + str(self.info["types"])
        for t,obj in self.types.iteritems():
            obj.print_info(l + 1)
        
    def parse_info(self,xml):
        d = defaultdict();
        r = xml.getroot()
        d["version"] = r.get("version")
        n = r.get("name")
        d["name"] = n
        d["types"] = []
        d["model"] = r.get("model")

        for e in r.findall("./memory/[@type]"):
            mem = Memory.Memory(e);
            dm = mem.get_info()
            d[dm["type"]] = dm
            d["types"].append(dm["type"])
            self.types[dm["type"]] = mem
                        
        return d

    def build_spec(self, spec, version, specification=False):
        s = spec.get_info()
        # TODO: Why does version = 14.1 fail?
        # TODO: Check Version
        if(version == "14.1" and not specification):
            r = ET.Element("board", attrib={"version": "0.9", "name":self.info["name"] + "_" + s["Name"]})
        else:
            r = ET.Element("board", attrib={"version": version, "name":self.info["name"] + "_" + s["Name"]})
        if(specification):
            r.set("file", self.info["name"]+".xml")

        # Summary of Resources
        resources = Counter({"alms":0,
                             "ffs":0,
                             "rams":0,
                             "dsps":0})
        
        for sys in s["Systems"]:
            t = s[sys]["Type"]
            resources.update(self.info[t]["resources"])

            for i in s[sys]["Interfaces"]:
                resources.update(self.info[t][i]["resources"])
        deve = ET.SubElement(r,"device", attrib={"device_model":self.info["model"]})
        re = ET.SubElement(deve,"used_resources")
        for rt,num in resources.iteritems():
            ET.SubElement(re, rt, attrib={"num":str(num)})

        base = 0
        size_default = 0
        for sys in s["Systems"]:
            t = s[sys]["Type"]
            m = self.types[t]
            e = m.build_spec(spec,sys,base,specification=specification)
            r.append(e)
            for i in s[sys]["Interfaces"]:
                base += int(s[sys][i]["Size"],16)
                if(sys == "0"):
                    size_default += int(s[sys][i]["Size"],16)

        # ACL Plumbing
        intfs = ET.SubElement(r, "interfaces")
        
        # TODO: What is the purpose of misc?
        kernel_cra = ET.SubElement(intfs,"interface",
                                   attrib={"name":"tinker",
                                            "port":"kernel_cra",
                                            "type":"master",
                                            "width":"64",
                                            "misc":"0"})

        kernel_irq = ET.SubElement(intfs,"interface",
                                   attrib={"name":"tinker",
                                           "port":"kernel_irq",
                                           "type":"irq",
                                           "width":"1"})
        snoop = ET.SubElement(intfs,"interface",
                              attrib={"name":"tinker",
                                      "port":"acl_internal_snoop",
                                      "type":"streamsource",
                                      "enable":"SNOOPENABLE",
                                      "clock":"tinker.kernel_clk",
                                      "width":str(int(math.log(size_default)/math.log(2)))})
        kclk_rst = ET.SubElement(intfs,"kernel_clk_reset",
                                 attrib={"clk":"tinker.kernel_clk",
                                         "clk2x":"tinker.kernel_clk2x",
                                         "reset":"tinker.kernel_reset"})
        # Host Interface
        host = ET.SubElement(r,"host")
        ET.SubElement(host,"kernel_config",
                      attrib={"start":"0x00000000","size":"0x0100000"})        
        return r

    def gen_macros(self, spec):
        s = spec.get_info()
        macros =""
        for sys in s["Systems"]:
            t = s[sys]["Type"]
            mem = self.types[t]
            macros += mem.gen_macros(spec, sys)
        return macros

    def gen_system(self, spec, sysxml):
        sysroot = ET.parse(sysxml).getroot()
        s = spec.get_info()
        for sys in s["Systems"]:
            t = s[sys]["Type"]
            for i in s[sys]["Interfaces"]:
                n = t.lower()+ "_" + i
                r = s[sys][i]["Role"]
                ET.SubElement(sysroot,"interface",
                              attrib={"name":n,
                                      "internal":"tinker."+n,
                                      "type":"conduit",
                                      "dir":"end"})
                if(r == "primary"):
                    ET.SubElement(sysroot,"interface",
                                  attrib={"name":n+"_mem_oct",
                                          "internal":"tinker."+n+"_oct",
                                          "type":"conduit",
                                          "dir":"end"})
                if(r == "primary" or r == "independent"):
                    ET.SubElement(sysroot,"interface",
                                  attrib={"name":n + "_pll_ref",
                                          "internal":"tinker."+n+"_pll_ref",
                                          "type":"conduit",
                                          "dir":"end"})
        return sysroot
