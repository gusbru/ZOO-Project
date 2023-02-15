import zoo
import sys
import osgeo.ogr
import osgeo.ogr as ogr

def echo(conf,inputs,outputs):
    print(inputs,file=sys.stderr)
    if "a" in inputs:
        outputs["a"]["value"]=inputs["a"]["value"]
        if "mimeType" in inputs["a"]:
            outputs["a"]["mimeType"]=inputs["a"]["mimeType"]
        if "mediaType" in inputs["a"]:
            outputs["a"]["mediaType"]=inputs["a"]["mediaType"]
        if "encoding" in inputs["a"]:
            outputs["a"]["encoding"]=inputs["a"]["encoding"]
    else:
        outputs["a"]["value"]="Empty"
    print(inputs,file=sys.stderr)
    if "b" in inputs and inputs["b"]["inRequest"]=="true":
        if "cache_file" in inputs["b"]:
            try:
                ds = osgeo.ogr.Open(inputs["b"]["cache_file"])
                path=""
                if outputs["b"]["mimeType"]=="application/json":
                    out_ds  = ogr.GetDriverByName("GeoJSON").CopyDataSource(ds, conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".json")
                    if out_ds is None:
                        raise Exception("Unable to parse GeoJSON")
                    path=conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".json"
                else:
                    out_ds  = ogr.GetDriverByName("GML").CopyDataSource(ds, conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".xml")
                    if out_ds is None:
                        raise Exception("Unable to parse GML")
                    path=conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".xml"
            except Exception as e:
                print("*******",file=sys.stderr)
                print(e,file=sys.stderr)
                print("*******",file=sys.stderr)
                path=conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".xml"
                f = open(path, "w+")
                f.write(inputs["b"]["value"])
                f.close()
                outputs["b"]["mimeType"]="text/xml"
                outputs["b"]["value"]=inputs["b"]["value"]
        else:
            try:
                import json
                lobj=json.loads(inputs["b"]["value"])
                path=conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".json"
                f = open(path, "w+")
                json.dump(lobj,f)
                outputs["b"]["mimeType"]="application/json"
            except Exception as e:
                print("*******",file=sys.stderr)
                print(e,file=sys.stderr)
                print("*******",file=sys.stderr)
                path=conf["main"]["tmpPath"]+"/result-"+conf["lenv"]["usid"]+".xml"
                f = open(path, "w+")
                f.write(inputs["b"]["value"])
                f.close()
                outputs["b"]["mimeType"]="text/xml"
                outputs["b"]["value"]=inputs["b"]["value"]
        outputs["b"]["generated_file"]=path
    else:
        outputs["b"]["value"]="Empty"
    if "c" in inputs:
        outputs["c"]["value"]=inputs["c"]["value"]
    else:
        outputs["c"]["value"]="Empty"
    if "pause" in inputs and inputs["pause"]["inRequest"]!="false":
        import time
        nb_sleep=inputs["pause"]["value"]
        for i in range(4):
            conf["lenv"]["message"]="Sleeping for "+inputs["pause"]["value"]+" seconds ("+str(i+1)+"/4)"
            zoo.update_status(conf,25*i)
            time.sleep((float(inputs["pause"]["value"])*25)/100)
    print(outputs,file=sys.stderr)
    return zoo.SERVICE_SUCCEEDED
