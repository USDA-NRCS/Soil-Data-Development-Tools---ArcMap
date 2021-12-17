# gSSURGO_CreateSoilMaps.py
#
# Batch-mode. Creates Soil Data Viewer-type maps using only the default settings. Designed to run in batch-mode.
# Cannot be used to generate maps for layers that require a primary or secondary constraint (ex. Ecological Site Name)

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
        PrintMsg("Unhandled error in attFld method", 2)
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
                arcpy.AddError(" \n" + string)

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
def elapsedTime(start):
    # Calculate amount of time since "start" and return time string
    try:
        # Stop timer
        #
        end = time.time()

        # Calculate total elapsed seconds
        eTotal = end - start

        # day = 86400 seconds
        # hour = 3600 seconds
        # minute = 60 seconds

        eMsg = ""

        # calculate elapsed days
        eDay1 = eTotal / 86400
        eDay2 = math.modf(eDay1)
        eDay = int(eDay2[1])
        eDayR = eDay2[0]

        if eDay > 1:
          eMsg = eMsg + str(eDay) + " days "
        elif eDay == 1:
          eMsg = eMsg + str(eDay) + " day "

        # Calculated elapsed hours
        eHour1 = eDayR * 24
        eHour2 = math.modf(eHour1)
        eHour = int(eHour2[1])
        eHourR = eHour2[0]

        if eDay > 0 or eHour > 0:
            if eHour > 1:
                eMsg = eMsg + str(eHour) + " hours "
            else:
                eMsg = eMsg + str(eHour) + " hour "

        # Calculate elapsed minutes
        eMinute1 = eHourR * 60
        eMinute2 = math.modf(eMinute1)
        eMinute = int(eMinute2[1])
        eMinuteR = eMinute2[0]

        if eDay > 0 or eHour > 0 or eMinute > 0:
            if eMinute > 1:
                eMsg = eMsg + str(eMinute) + " minutes "
            else:
                eMsg = eMsg + str(eMinute) + " minute "

        # Calculate elapsed secons
        eSeconds = "%.1f" % (eMinuteR * 60)

        if eSeconds == "1.00":
            eMsg = eMsg + eSeconds + " second "
        else:
            eMsg = eMsg + eSeconds + " seconds "

        return eMsg

    except:
        errorMsg()
        return ""

## ===================================================================================
def CreateGroupLayer(grpLayerName, mxd, df):
    try:
        # Use template lyr file stored in current script directory to create new Group Layer
        # This SDVGroupLayer.lyr file must be part of the install package along with
        # any used for symbology. The name property will be changed later.
        #
        # arcpy.mapping.AddLayerToGroup(df, grpLayer, dInterpLayers[sdvAtt], "BOTTOM")
        #
        grpLayerFile = os.path.join(os.path.dirname(sys.argv[0]), "SDV_GroupLayer.lyr")

        if not arcpy.Exists(grpLayerFile):
            raise MyError, "Missing group layer file (" + grpLayerFile + ")"

        testLayers = arcpy.mapping.ListLayers(mxd, grpLayerName, df)

        if len(testLayers) > 0:
            # Using existing group layer
            grpLayer = testLayers[0]

        else:
            # Group layer does not exist, make a new one
            grpLayer = arcpy.mapping.Layer(grpLayerFile)  # template group layer file
            grpLayer.visible = False
            grpLayer.name = grpLayerName
            grpLayer.description = "Group layer containing soil map layers based upon vector or raster data"
            grpLayer.visible = False
            arcpy.mapping.AddLayer(df, grpLayer, "TOP")

        #PrintMsg(" \nAdding group layer: " + str(grpLayer.name), 0)

        return grpLayer

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return None

    except:
        errorMsg()
        return None

## ===================================================================================
## MAIN
## ===================================================================================

# Import system modules
import arcpy, sys, string, os, traceback, locale, time, sqlite3

# Create the environment
from arcpy import env

try:

    inputLayer = arcpy.GetParameterAsText(0)       # Input mapunit polygon layer
    sdvAtts = arcpy.GetParameter(1)                # SDV Attribute
    depthList = arcpy.GetParameterAsText(2)        # space-delimited list of depths

    num = 0
    failedList = list()
    PrintMsg(" \n", 0)
    import gSSURGO_CreateSoilMap

    # Turn off display of the inputLayer to reduce potential screen redraws
    mxd = arcpy.mapping.MapDocument("CURRENT")
    df = mxd.activeDataFrame
    layers = arcpy.mapping.ListLayers(mxd, inputLayer, df)
    
    if len(layers) == 1:
        soilLayer = layers[0]
        soilLayer.visible = False
        del soilLayer

    del layers

    # Get gSSURGO DB behind inputLayer
    desc = arcpy.Describe(inputLayer)
    inputType = desc.dataType.lower()
    
    if inputType == "featurelayer":
        fc = desc.featureclass.catalogPath
        gdb = os.path.dirname(fc)

    elif inputType == "rasterlayer":
        gdb = os.path.dirname(desc.catalogPath)

    aggMethod = ""
    primCst = ""
    secCst = ""
    begMo = "January"
    endMo = "December"
    bZero = True
    cutOff = 0
    bFuzzy = False
    bNulls = True
    tieBreaker = ""
    sRV = "Representative"

    # Set up depth ranges using space delimited list of break values from parameter string
    # ex. 0 10 25 ...
    depthRanges = list()
    d1 = depthList.split(" ")
    d2 = [int(x) for x in d1]

    for i in range(len(d2) - 1):
        depthRanges.append((d2[i], d2[i + 1]))

    depthRanges.reverse()
    newAtts = list()
      
    # Need logic to decide whether group layer hierarchy will work.
    # If user did not consistently select folder names in menu, that might be a problem
    dGroups = dict()
    groupList = list()

    if str(sdvAtts).find("*") >= 0:
        # Use folder names as group layers
        # Define tables used to populate the first "SDV Folder" choice list
        sdvFolderTbl = os.path.join(gdb, "sdvfolder")
        sdvFolderAttTbl = os.path.join(gdb, "sdvfolderattribute")
        sdvAttTbl = os.path.join(gdb, "sdvattribute")
        sdvQuery = os.path.join("IN_MEMORY", "SDVQueryTbl")
        arcpy.MakeQueryTable_management([sdvAttTbl, sdvFolderAttTbl, sdvFolderTbl], sdvQuery, "USE_KEY_FIELDS", "#", [["sdvattribute.attributename", "attributename"],["sdvfolder.foldersequence", "foldersequence"], ["sdvfolder.foldername", "foldername"]], "sdvattribute.attributekey = sdvfolderattribute.attributekey AND sdvfolderattribute.folderkey = sdvfolder.folderkey")

        with arcpy.da.SearchCursor(sdvQuery, ["sdvfolder.foldersequence", "sdvattribute.attributename", "sdvfolder.foldername"], sql_clause=(None, "ORDER BY sdvfolder.foldersequence, sdvattribute.attributename")) as cur:
            for rec in cur:
                dGroups[rec[1].encode('ascii')] = rec[2].encode('ascii').upper()
        
        #PrintMsg("\n" + str(sdvAtts), 0)
        
        for sdvAtt in sdvAtts:
            att = sdvAtt.strip()
            
            if not att.startswith("*"):
                # this is an attribute
                newAtts.append(att)
            
    else:
        # No group layers
        for sdvAtt in sdvAtts:
            att = sdvAtt.strip()
            newAtts.append(att)
            dGroups[att] = ""


    # Create list of soil maps that use horizon-level attributes
    #
    flds3 = ["attributename", "depthqualifiermode"]
    sql2 = "attributetablename = 'chorizon'"
    #sql2 = "attributetablename = 'chorizon' and not depthqualifiermode = 'Surface Layer'"
    hzAtts = list()
    surfaceAtts = list()
    sdvTbl = os.path.join(gdb, "sdvattribute")

    with arcpy.da.SearchCursor(sdvTbl, flds3, where_clause=sql2) as aCur:
        # populate list of sdv attribute names

        for rec in aCur:
            att = rec[0]
            dq = rec[1]

            if att in newAtts and not att in hzAtts and dq != 'Surface Layer':
                hzAtts.append(att) # accumulate sdv attribute names that use horizon data

            if att in newAtts and dq == 'Surface Layer':
                surfaceAtts.append(att)

    hzAtts.sort()

    # Calculate the number of new map layers that will be created:
    hzMaps = (len(hzAtts) * len(depthRanges) )
    individualMaps = (len(newAtts) - len(hzAtts))
    mapCnt = hzMaps + individualMaps

    if hzMaps > 0:
        PrintMsg(" \nCreating a series of " + str(mapCnt) + " soil maps (" + str(individualMaps) + " individual map(s) plus " + str(hzMaps) + " horizon-level property maps)", 0)

    else:
        PrintMsg(" \nCreating a series of " + str(mapCnt) + " soil maps", 0)

    arcpy.SetProgressor("step", "Creating series of soil maps...", 0, mapCnt, 1)
    num = 0
    
    for sdvAtt in newAtts:

        grpName = dGroups[sdvAtt]

        if not grpName == "":
            if inputType == "featurelayer":
                grpLayerName = grpName + "  (Polygon)"

            else:
                grpLayerName = grpName + "  (Raster)"

            if len(groupList) > 0:
                # Save the current group layer to a layerfile before moving on to the next
                lyrName = groupList[-1]
                grpLayerFile = os.path.join(os.path.dirname(gdb), lyrName)
                arcpy.SaveToLayerFile_management(grpLayer, grpLayerFile)
                                                 
            grpLayer = CreateGroupLayer(grpLayerName, mxd, df)  
            groupList.append(grpLayerName)

        else:
            grpLayer = None
            grpLayerName = ""

        if sdvAtt in hzAtts:

            # This will only process data when there is a set of depth ranges specified
            #
            # I need to handle this differently when no depths are entered
            #
            for depths in depthRanges:
                top, bot = depths
                num += 1
                msg = "Creating hz map number " + str(num) + ":  " + sdvAtt + " " + str(top) + " to " + str(bot) + "cm"
                    
                arcpy.SetProgressorLabel(msg)
                PrintMsg(" \n" + msg, 0)
                time.sleep(2)

                # Trying here to enter default values for most parameters and to modify CreateSoilMap.CreateSoilMap to use default aggregation method (aggMethod) when it is passed an empty string
                dfName = df.name
                finalMapLayer = gSSURGO_CreateSoilMap.CreateSoilMap(inputLayer, sdvAtt, aggMethod, primCst, secCst, top, bot, begMo, endMo, tieBreaker, bZero, cutOff, bFuzzy, sRV, grpLayerName, mxd, dfName) # external script

                if finalMapLayer is None:
                    #PrintMsg("\tGot back None1 from gSSURGO_CreateSoilMap.CreateSoilMap for " + sdvAtt, 1)
                    
                    if not sdvAtt in failedList:
                        failedList.append(sdvAtt)

                else:
                    df = mxd.activeDataFrame
                    newLayer = arcpy.mapping.ListLayers(mxd, finalMapLayer.name, df)[0]
                    
                arcpy.SetProgressorPosition()

        else:
            top, bot = (0, 1)  # this should cover the surface properties such as Texture
            num += 1

            if sdvAtt in surfaceAtts:
                msg = "Creating map number " + str(num) + ":  " + sdvAtt + " (surface)"

            else:     
                msg = "Creating map number " + str(num) + ":  " + sdvAtt
      
            arcpy.SetProgressorLabel(msg)
            PrintMsg(" \n" + msg, 0)
            time.sleep(2)

            # Trying to enter default values for most parameters and to modify CreateSoilMap.CreateSoilMap to use default aggregation method (aggMethod) when it is passed an empty string
            dfName = df.name
            finalMapLayer = gSSURGO_CreateSoilMap.CreateSoilMap(inputLayer, sdvAtt, aggMethod, primCst, secCst, top, bot, begMo, endMo, tieBreaker, bZero, cutOff, bFuzzy, sRV, grpLayerName, mxd, dfName) # external script
            
            if finalMapLayer is None:
                #PrintMsg("\tGot back None2 from gSSURGO_CreateSoilMap.CreateSoilMap for " + sdvAtt, 1)
                
                if not sdvAtt in failedList:
                    failedList.append(sdvAtt)

            else:
                # PrintMsg(" \n2. Adding Final Map Layer Name: '" + finalMapLayer.name + "' to " + grpLayerName, 1)
                newLayer = arcpy.mapping.ListLayers(mxd, finalMapLayer.name, df)[0]
            
            arcpy.SetProgressorPosition()

            # Original CreateSoilMap returns integer value for status. Trying to switch to returning maplayer object.
            #
            # Return values will control how the rest of the maps will be handled
            #
            #  1 Successful
            # -1 No data
            # -2 raised error
            #  0 Error
                    
    arcpy.RefreshActiveView()
    
    if len(failedList) > 0:
 
        if len(failedList) == 1:
            PrintMsg(" \nUnable to create soil map layers for this attribute: '" + failedList[0] + "' \n ", 1)

        else:
            PrintMsg(" \nUnable to create soil map layers for these attributes: '" + "', '".join(failedList) + "' \n ", 1)

    else:
        PrintMsg(" \nCreateSoilMaps finished \n ", 0)

    del failedList
    
except MyError, e:
    PrintMsg(str(e), 2)
    
except:
    errorMsg()

finally:
    try:
        del mxd, df

    except:
        pass
