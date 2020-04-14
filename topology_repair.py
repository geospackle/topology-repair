import os
import arcpy
import pandas as pd


def topology_repair(
    inFile=[path to shapefile], 
    dissolve_field="TYPE", 
    gap_threshold=10000):    # threshold is max area of gaps that are considered to be errors

    # create variables for necessary paths, create gdb, import inFile into feature dataset
    gdb = os.path.basename(inFile[:-3] + 'gdb')
    gdbDir= os.path.dirname(inFile)
    arcpy.CreateFileGDB_management(gdbDir, gdb)
    arcpy.env.workspace = gdbDir + '/' + gdb
    feature_ds = arcpy.env.workspace + '/topology_ds'
    data = arcpy.env.workspace + '/topology_ds/' + os.path.basename(inFile[:-4])
    topology = feature_ds + '/Topology'
    arcpy.CreateFeatureDataset_management(arcpy.env.workspace, "topology_ds", inFile[:-3] + 'prj')
    arcpy.FeatureClassToGeodatabase_conversion([inFile], "topology_ds")

    # Create topology, add feature class, define rules
    arcpy.CreateTopology_management(feature_ds, "Topology")
    arcpy.AddFeatureClassToTopology_management(topology, data)
    arcpy.AddRuleToTopology_management(topology, "Must Not Overlap (Area)",data,"","","")
    arcpy.ValidateTopology_management(topology)

    # create polygon inFile from errors and delete
    arcpy.ExportTopologyErrors_management(topology, "", "overlapErrors")
    arcpy.AddField_management("overlapErrors_poly", dissolve_field, "STRING")
    o = "o"
    arcpy.CalculateField_management('overlapErrors_poly', dissolve_field,o)

    # Create topology, add feature class, define rules
    arcpy.CreateTopology_management(feature_ds, "Topology")
    arcpy.AddFeatureClassToTopology_management(topology, data)
    arcpy.AddRuleToTopology_management(topology, "Must Not Have Gaps (Area)",data,"","","")
    arcpy.ValidateTopology_management(topology)

    # create polygon inFile from errors and merge with original data
    arcpy.ExportTopologyErrors_management(topology, "", "gapErrors")
    arcpy.FeatureToPolygon_management("gapErrors_line","topo_errors_gaps")
    arcpy.SelectLayerByAttribute_management ("topo_errors_gaps", "NEW_SELECTION", '"Shape_Area" < ' + str(gap_threshold))
    arcpy.AddField_management("topo_errors_gaps", dissolve_field, "STRING")
    g = "g"
    arcpy.CalculateField_management('topo_errors_gaps', dissolve_field,g )
    arcpy.SelectLayerByAttribute_management ("topo_errors_gaps", "SWITCH_SELECTION")
    arcpy.DeleteRows_management("topo_errors_gaps")
    arcpy.Merge_management(["overlapErrors_poly", "topo_errors_gaps" ,inFile],"topomerged")

    # Get neighbor table and export to gdb
    arcpy.PolygonNeighbors_analysis('topomerged', 'topo_errors',['OBJECTID', dissolve_field])  # doesn't always find neighbors on all sides of polygon
    arcpy.TableToGeodatabase_conversion('topo_errors',arcpy.env.workspace)

    #table to array and array to dataframe
    nbr_field = 'nbr_' + dissolve_field
    arr = arcpy.da.FeatureClassToNumPyArray(("topo_errors"), ("src_OBJECTID", nbr_field, "LENGTH"))
    index = [str(i) for i in range(1, len(arr)+1)]
    df = pd.DataFrame(arr, index=index)
    df = df.groupby(['src_OBJECTID','nbr_TYPE'],as_index = False)['LENGTH'].sum()   #sum in case several sides of polygon have same neighbor

    #select rows from df and export to csv and to gdb
    idx = df.groupby(['src_OBJECTID'])['LENGTH'].transform(max) == df['LENGTH']
    df_select = df [idx]
    df_select.to_csv(gdbDir+'/joinme.csv', index=False)
    arcpy.TableToTable_conversion(gdbDir+'/joinme.csv', arcpy.env.workspace, "joinme")

    # Merge error polygons, join field, delete overlaps from infile, assign type to error polygons, merge all and dissolve
    arcpy.JoinField_management('topomerged', 'OBJECTID', 'joinme', 'src_OBJECTID', 'nbr_TYPE')
    arcpy.FeatureClassToFeatureClass_conversion('topomerged', "", 'topo_errors_join')
    arcpy.SelectLayerByAttribute_management("topo_errors_join", "NEW_SELECTION", "TYPE = 'o'")
    arcpy.SelectLayerByAttribute_management("topo_errors_join", "ADD_TO_SELECTION", "TYPE = 'g'")
    arcpy.SelectLayerByAttribute_management ("topo_errors_join", "SWITCH_SELECTION")
    arcpy.DeleteRows_management("topo_errors_join")   #leave only error polygons
    arcpy.AlterField_management('topo_errors_join', 'TYPE', 'orig_TYPE','orig_TYPE')
    arcpy.AlterField_management('topo_errors_join', 'nbr_TYPE', 'TYPE','TYPE')
    arcpy.Erase_analysis(inFile,'overlapErrors_poly','infile_overlaps_erased')
    arcpy.Merge_management(["topo_errors_join","infile_overlaps_erased"],"merged_neighbors")
    arcpy.Dissolve_management('merged_neighbors', 'dissolved_neighbors', 'TYPE')
