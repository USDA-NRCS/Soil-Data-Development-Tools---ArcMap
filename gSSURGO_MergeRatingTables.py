# SDVSave_10.py
#
# Steve Peaslee, National Soil Survey Center
# March 14, 2013
#
# Purpose: Merge Soil Data Viewer map layers into a single geodatabase featureclass
# and preserve symbology for each layer.
#
# ArcGIS 10.0 - SP5
# This version is NOT compatible with ArcGIS 9.x!
# ArcGIS 10.1 - SP1
# Altered input parameter 0 to make it act like a list instead of a value table
# Problems with updating layer source when a personal geodatabase is used. For now
# I am going to remove Personal geodatabase as an output option.
# 2014-03-28 Updated some issues with qualified field names being used in output aliases
# Fixed duplicate field handling error
# 2014-08-20 Ian Reid reported a problem when outputting to a featuredataset. Found out that
# the method 'replaceDataSource' always requires the name of the geodatabase, not the full
# path to the featuredataset. Counterintuitive.

# Uses arcpy.mapping functions
#
## ===================================================================================
class MyError(Exception):
    pass

## ===================================================================================
def errorMsg():
    try:
        tb = sys.exc_info()[2]
        tbinfo = traceback.format_tb(tb)[0]
        theMsg = tbinfo + " \n" + str(sys.exc_type)+ ": " + str(sys.exc_value) + " \n"
        PrintMsg(theMsg, 2)

    except:
        PrintMsg("Unhandled error in errorMsg method", 2)
        pass

## ===================================================================================
def PrintMsg(msg, severity=0):
    # Adds tool message to the geoprocessor
    #
    #Split the message on \n first, so that if it's multiple lines, a GPMessage will be added for each line
    try:
        for string in msg.split('\n'):
            #Add a geoprocessing message (in case this is run as a tool)
            if severity == 0:
                arcpy.AddMessage(string)

            elif severity == 1:
                arcpy.AddWarning(string)

            elif severity == 2:
                arcpy.AddMessage("    ")
                arcpy.AddError(string)

    except:
        pass

## ===================================================================================
def Number_Format(num, places=0, bCommas=True):
    try:
    # Format a number according to locality and given places
        locale.setlocale(locale.LC_ALL, "")
        if bCommas:
            theNumber = locale.format("%.*f", (places, num), True)

        else:
            theNumber = locale.format("%.*f", (places, num), False)
        return theNumber

    except:
        errorMsg()

        return "???"

## ===================================================================================
def CreateMergedTable(sdvLayers, outputTbl):
    # Merge rating tables from for the selected soilmap layers to create a single, mapunit-level table
    #
    try:
        # Get number of SDV layers selected for export
        #sdvLayers = sdvLayers.split(";")  # switch from semi-colon-delimited string to list of layer names
        #numLayers = len(sdvLayers)      # ArcGIS 10.1 returns count for list object

        env.overwriteOutput = True # Overwrite existing output tables

        # Tool validation code is supposed to prevent duplicate output tables

        # Get arcpy mapping objects
        thisMXD = arcpy.mapping.MapDocument("CURRENT")
        mLayers = arcpy.mapping.ListLayers(thisMXD)

        # Probably should make sure all of these input layers have the same featureclass
        #
        # first get path where input SDV shapefiles are located (using last one in list)
        # hopefully each layer is based upon the same set of polygons
        #
        # First check each input table to make sure there are no duplicate rating fields
        # Begin by getting adding fields from the input shapefile (lastShp). This is necessary
        # to avoid duplication such as MUNAME which may often exist in a county shapefile.
        #
        # Very important. Make sure that a base table is created having ALL mukeys. Individual SDV rating
        # tables might conceivably be missing un-rated mukeys.

        chkFields = list()  # list of rating fields from SDV soil map layers (basenames). Use this to count dups.
        #dFields = dict()
        dLayerFields = dict()
        maxRecords = 0  # use this to determine which table has the most records and put it first
        maxTable = ""
        layersByField = dict()
        textFields = list()
        #tmpTbl = os.path.join(env.scratchGDB, "TmpMerge")


        # Iterate through each of the layers and get its rating field
        for sdvLayer in sdvLayers:

            if sdvLayer.startswith("'") and sdvLayer.endswith("'"):
                sdvLayer = sdvLayers[i][1:-1]  # this is dropping first and last char in name for RUSLE2 maps..

            desc = arcpy.Describe(sdvLayer)
            dataType = desc.dataType

            if dataType == "FeatureLayer":
                gdb = os.path.dirname(desc.featureclass.catalogPath)

            elif dataType == "RasterLayer":
                gdb = os.path.dirname(desc.catalogPath)

            else:
                raise MyError, "Soil map datatype (" + dataType + ") not valid"

            allFields = desc.fields
            ratingField = allFields[-1]  # rating field should be the last one in the table
            #fName = ratingField.name.encode('ascii')       # fully qualified name in join
            bName = ratingField.baseName.encode('ascii')   # physical name
            fName = ratingField.name.encode('ascii')   # physical name

            clipLen = (-1 * (len(bName))) - 1
            sdvTblName = fName[0:clipLen]
            sdvTbl = os.path.join(gdb, sdvTblName)
            newName = sdvTblName[4:]
            allFields = arcpy.Describe(sdvTbl).fields

            fldType = ratingField.type
            fldLen = ratingField.length
            fldAlias = bName + ", " + sdvTblName  # ? this isn't working
            fldAlias = newName.replace("_", " ")  # try creating alias by replacing underscores with spaces
            dLayerFields[sdvLayer] = (sdvTblName, bName, newName, fldType, fldLen, fldAlias, allFields)
            chkFields.append(newName)
            layersByField[newName.upper()] = sdvLayer
            #PrintMsg("\nField type for " + sdvLayer + " is " + fldType, 1)

            if fldType.upper() in ["STRING", "SMALLINTEGER"]:
                textFields.append(newName)

            # get record count for sdvTbl
            recCnt = int(arcpy.GetCount_management(sdvTbl).getOutput(0))


        # Put the selected 'master' table at the front of the list. Usually this will be the one with
        # the largest number of records, but for USGS project I am putting MUNAME up front because most
        # of the tables contain data for the entire CONUS, and I only want the western states.
        i = 0

        for sdvLayer in sdvLayers:

            if sdvLayer.startswith("'"):
                sdvLayer = sdvLayers[i][1:-1]  # this is dropping first and last char in name for RUSLE2 maps..

            PrintMsg(" \n\t" + str(i + 1) + ". Processing sdvLayer: " + sdvLayer, 0)
            desc = arcpy.Describe(sdvLayer)
            dataType = desc.dataType

            if dataType == "FeatureLayer":
                gdb = os.path.dirname(desc.featureclass.catalogPath)

            elif dataType == "RasterLayer":
                gdb = os.path.dirname(desc.catalogPath)

            else:
                raise MyError, "Soil map datatype (" + dataType + ") not valid"

            sdvTblName, bName, newName, fldType, fldLen, fldAlias, allFields = dLayerFields[sdvLayer]
            sdvTbl = os.path.join(gdb, sdvTblName)

            inputFields = [fld.name.upper() for fld in allFields]
            # PrintMsg("\t" + sdvLayer + ": " + ", ".join(inputFields), 1)

            if i == 0:

                # Use mapunit table as base for the output table. mukey, musym, muname
                mapunitTbl = os.path.join(gdb, "mapunit")
                muFields = ["mukey", "musym", "muname"]

                if not arcpy.Exists(mapunitTbl):
                    raise MyError, "Missing required table: " + mapunitTbl

                arcpy.Sort_management(mapunitTbl, outputTbl, "mukey")
                cntMapunits = int(arcpy.GetCount_management(outputTbl).getOutput(0))

                # identify columns from the original mapunit table that are not required for the output table
                dropFields = [fld.name.lower() for fld in arcpy.Describe(outputTbl).fields if not fld.name.lower() in muFields and fld.type != 'OID']
                # PrintMsg(" \nDropping " + ", ".join(dropFields) + " fields from output table", 1)
                arcpy.DeleteField_management(outputTbl, dropFields)

                #PrintMsg("\t\tAdding " + pctName + " column to " + os.path.basename(tmpTbl), 0)
                if "COMPPCT_R" in inputFields:
                    pctName = "pct_" + newName
                    pctAlias = pctName.replace("_", " ")
                    #arcpy.AddField_management(outputTbl, pctName, "SHORT", "", "", "", pctName.replace("_", " "))
                    #PrintMsg("\t\tAdding " + newName + " column...", 0)
                    inFields = ["mukey", "comppct_r", bName]
                    outFields = ["mukey", pctName, newName]
                    dRatings = dict()

                    with arcpy.da.SearchCursor(sdvTbl, inFields) as incur:
                        iCnt = 0
                        for rec in incur:
                            iCnt += 1
                            mukey, comppct, rating = rec
                            dRatings[mukey] = (comppct, rating)

                    #arcpy.DeleteField_management(outputTbl, "comppct_r")
                    #arcpy.DeleteField_management(outputTbl, bName)
                    outFields = ["mukey", pctName, newName]
                    arcpy.AddField_management(outputTbl, pctName, "SHORT", "", "", "", pctAlias)
                    arcpy.AddField_management(outputTbl, newName, fldType, "", "", fldLen, fldAlias)
                    arcpy.SetProgressor("step", "Updating output table with data (" + Number_Format(len(dRatings), 0 , True) + " values) from " + sdvLayer, 0, cntMapunits, 1)

                    with arcpy.da.UpdateCursor(outputTbl, outFields) as outcur:
                        for rec in outcur:
                            try:
                                mukey = rec[0]
                                comppct = dRatings[mukey][0]
                                rating = dRatings[mukey][1]
                                rec[1] = comppct
                                rec[2] = rating
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()

                            except KeyError:
                                rec[1] = None
                                rec[2] = None
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()
                                #PrintMsg("\tMissing " + fName + " data for " + mukey, 1)

                else:
                    inFields = ["mukey", bName]
                    outFields = ["mukey", newName]
                    dRatings = dict()

                    with arcpy.da.SearchCursor(sdvTbl, inFields) as incur:
                        iCnt = 0
                        for rec in incur:
                            iCnt += 1
                            mukey, rating = rec
                            dRatings[mukey] = rating

                    #arcpy.DeleteField_management(outputTbl, bName)
                    outFields = ["mukey", newName]
                    arcpy.AddField_management(outputTbl, newName, fldType, "", "", fldLen, fldAlias)
                    arcpy.SetProgressor("step", "Updating output table with data (" + Number_Format(len(dRatings), 0 , True) + " values) from " + sdvLayer, 0, cntMapunits, 1)

                    with arcpy.da.UpdateCursor(outputTbl, outFields) as outcur:
                        for rec in outcur:
                            try:
                                mukey = rec[0]
                                rating = dRatings[mukey]
                                rec[1] = rating
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()

                            except KeyError:
                                rec[1] = None
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()
                                #PrintMsg("\tMissing " + fName + " data for " + mukey, 1)

                del dRatings

            else:
                pctName = "pct_" + newName
                pctAlias = pctName.replace("_", " ")

                if chkFields.count(newName) == 1:
                    # bName is a unique field name
                    # Append the just the rating column to the tmpTbl

                    #PrintMsg("\t\tAdding " + pctName + " column to " + os.path.basename(tmpTbl), 0)
                    if "COMPPCT_R" in inputFields:
                        arcpy.AddField_management(outputTbl, pctName, "SHORT", "", "", "", pctAlias)


                        #PrintMsg("\t\tAdding " + newName + " column...", 0)
                        inFields = ["mukey", "comppct_r", bName]
                        outFields = ["mukey", pctName, newName]

                    else:
                        inFields = ["mukey", bName]
                        outFields = ["mukey", newName]

##                    PrintMsg("---------------------------")
##                    PrintMsg(outputTbl)
##                    PrintMsg(newName)
##                    PrintMsg(str([f.name for f in arcpy.ListFields(outputTbl)]))
                    if not newName.lower() in [f.name.lower() for f in arcpy.ListFields(outputTbl)]:
                        arcpy.AddField_management(outputTbl, newName, fldType, "", "", fldLen, fldAlias)
                        time.sleep(1)

                else:
                    #PrintMsg(" \nCheckFields list: " + ", ".join(chkFields), 1)
                    raise MyError, "This is not a unique field name: " + newName

                dRatings = dict()

                # PrintMsg(" \nInput fields: " + ", ".join(inFields), 1)

                if "COMPPCT_R" in inputFields:
                    inFields = ["mukey", "comppct_r", bName]
                    outFields = ["mukey", pctName, newName]

                    with arcpy.da.SearchCursor(sdvTbl, inFields) as incur:
                        iCnt = 0
                        for rec in incur:
                            iCnt += 1
                            mukey, pct, rating = rec
                            dRatings[mukey] = [pct, rating]

                    arcpy.SetProgressor("step", "Updating output table with data (" + Number_Format(len(dRatings), 0 , True) + " values) from " + sdvLayer, 0, cntMapunits, 1)

                    with arcpy.da.UpdateCursor(outputTbl, outFields) as outcur:
                        for rec in outcur:
                            try:
                                mukey = rec[0]
                                pct, rating = dRatings[mukey]
                                rec[1] = pct
                                rec[2] = rating
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()

                            except KeyError:
                                rec[1] = None
                                rec[2] = None
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()
                                #PrintMsg("\tMissing " + fName + " data for " + mukey, 1)

                else:
                    inFields = ["mukey", bName]
                    outFields = ["mukey", newName]

                    with arcpy.da.SearchCursor(sdvTbl, inFields) as incur:
                        iCnt = 0
                        for rec in incur:
                            iCnt += 1
                            mukey, rating = rec
                            dRatings[mukey] = rating

                    arcpy.SetProgressor("step", "Updating output table with data (" + Number_Format(len(dRatings), 0 , True) + " values) from " + sdvLayer, 0, cntMapunits, 1)

                    with arcpy.da.UpdateCursor(outputTbl, outFields) as outcur:
                        for rec in outcur:
                            try:
                                mukey = rec[0]
                                rating = dRatings[mukey]
                                rec[1] = rating
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()

                            except KeyError:
                                rec[1] = None
                                outcur.updateRow(rec)
                                arcpy.SetProgressorPosition()
                                #PrintMsg("\tMissing " + fName + " data for " + mukey, 1)

                            except:
                                raise MyError, str(rec)

                del sdvTbl
            i += 1

        #arcpy.Sort_management(tmpTbl, outputTbl, "mukey")

        # I could probably switch out the individual rating table joins with the merged table right here??
        PrintMsg(" \nAdding field indexes to: " + ", ".join(textFields), 0)
        arcpy.AddIndex_management(outputTbl, ["mukey"], "Indx_" + os.path.basename(outputTbl) + "_Mukey")

        arcpy.SetProgressor("step", "Updating output table indexes...", 0, len(textFields), 1)

        for fldName in textFields:
            indxName = "Indx_SDV_" + fldName
            arcpy.AddIndex_management(outputTbl, [fldName], indxName)


        PrintMsg(" \nMerged ratings table: " + str(outputTbl) + " \n ", 0)

        return True

    except MyError, e:
        PrintMsg(str(e) + " \n", 2)
        try:
            del thisMXD
        except:
            pass
        return False

    except:
        errorMsg()
        try:
            del thisMXD
        except:
            pass
        return False

# ====================================================================================
## ====================================== Main Body ==================================
# Import modules
import sys, string, os, locale, traceback, arcpy
from arcpy import env

try:


    if __name__ == "__main__":
        # Create a single table that contains
        #sdvLayers = arcpy.GetParameterAsText(0)           # 10.1 List of string values representing temporary SDV layers from ArcMap TOC
        sdvLayers = arcpy.GetParameter(0)           # 10.1 List of string values representing temporary SDV layers from ArcMap TOC
        outputTbl = arcpy.GetParameterAsText(1)      # Output featureclass (preferably in a geodatabase)

        bMerged = CreateMergedTable(sdvLayers, outputTbl)


except arcpy.ExecuteError:
    #arcpy.AddError(arcpy.GetMessages(2))
    errorMsg()

except MyError, e:
    # Example: raise MyError("this is an error message")
    PrintMsg(str(e) + " \n", 2)

except:
    errorMsg()

