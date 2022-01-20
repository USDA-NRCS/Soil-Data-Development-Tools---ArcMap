# SSURGO_Convert_to_GeodatabaseF.py

# Alternative processing method. Import tabular data one table at a time.
#
# ArcGIS 10.1 (10.2 mostly works except for automtically updating metadata)
#
# Steve Peaslee, National Soil Survey Center, Lincoln, Nebraska
#
# Purpose: allow batch appending of SSURGO soil shapefiles and soil attribute tables into a single file geodatabase (10.0).

# Requires input dataset structure to follow the NRCS standard for Geospatial data (eg. soil_ne109\spatial and soil_ne109/tabular)
#
# Merge order is based upon sorted extent coordinates

# For the attribute data, we use an XML workspace document to define FGDB schema and read the tables from the SSURGO template database.
# These xml files should reside in the same folder as this script. See the GetML function for more info.
#
# Things yet to do:
#
# 1. Update metadata for each XML workspace document
# 2. Test implementation of ITRF00 datum transformation

# 11-15-2013 Added 'bailout' if one of the input template database tables is not found
# 11-22-2013
# 12-09-2013 Added option for automatically inserting featureclass alias for ArcGIS 10.1 and above
#
# 12-13-2013 Changed datum transformation method to always use ITRF00
#
# 01-04-2014 Added tabular metadata and automated the inclusion of state name and soil survey areas to metadata.
# 01-08-2014 Still need to automate metadata dates and gSSURGO process steps
# 01-09-2014 Removed hard-coded path to XML metadata translator file to make it 10.2 compatible
# 2014-09-27
# 2014-10-31 Added text file import to this script. Need to clean this up and make
#            it an option to the normal Access database import.
#
# In 2014, the folders within the WSS-SSURGO Download zipfiles were renamed to AREASYMBOL (uppercase)
# instead of soil_[AREASYMBOL]
# 2015-10-21 Modified tabular import to truncate string values to match field length
#
# 2015-11-13 Added import for metadata files so that up-to-date information will be used. These
#            tables have information about tables, columns, relationships and domain values.
#
# 2015-12-08 Added check for SSURGO version number (schema version). Hardcoded as 2 for gSSURGO.
#
# 2015-12-15 Incorporated primary key unique value constraint on sdv* tables as is done for the Access databases.
#
# 2016-03-15 Tabular import now uses CP1252 so that csv import of ESIS data won't error.
#
# 2017-06-28 Problem with metadata import.

#    arcpy.ExportMetadata_conversion (target, mdTranslator, mdExport)
#    <class 'arcgisscripting.ExecuteError'>: Failed to execute. Parameters are not valid.
#    ERROR 000584: Implementation of this Tool's Validate is invalid
#
# 2017-08-16 Added attribute index on rulekey, mrulekey for cointerp table.

# Need to remove DVD option from Transfer in XML Workspace document and
# replace with hard drive option.

# Offline media: External Drive
# Recording format: NTFS 3.0

# 2018-11-27. Fixed recent problem with relationshipclasses. Origin and destination tables were switched resulting in key-null errors if
# an attempt was made to delete any records.

# 2019-09-24. Remove the following columns from cointerp table and modified the .csv import:
#
# interpll
# interpllc
# interplr
# interplrc
# interphh
# interphhc

# 2020-03-30. Removed the above columns from the ImportTables function as well.

# 2021-11-30. Modified gSSURGO function to handle multiple SSURGO download naming conventions. - AD
#


## ===================================================================================
class MyError(Exception):
    pass

## ===================================================================================
def errorMsg():
    try:
        excInfo = sys.exc_info()
        tb = excInfo[2]
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
        #PrintMsg("Unhandled exception in Number_Format function (" + str(num) + ")", 2)
        return "???"

## ===================================================================================
def AddNewFields(outputShp, columnNames, columnInfo):
    # TEMPORARY CODE
    #
    # Create the empty output table that will contain the data from Soil Data Access
    #
    # ColumnNames and columnInfo come from the Attribute query JSON string
    # MUKEY would normally be included in the list, but it should already exist in the output featureclass
    #
    # Problem using temporary, IN_MEMORY table and JoinField with shapefiles to add new columns. Really slow performance.

    try:
        # Dictionary: SQL Server to FGDB
        #PrintMsg(" \nAddNewFields function begins", 1)
        dType = dict()

        dType["int"] = "long"
        dType["smallint"] = "short"
        dType["bit"] = "short"
        dType["varbinary"] = "blob"
        dType["nvarchar"] = "text"
        dType["varchar"] = "text"
        dType["char"] = "text"
        dType["datetime"] = "date"
        dType["datetime2"] = "date"
        dType["smalldatetime"] = "date"
        dType["decimal"] = "double"
        dType["numeric"] = "double"
        dType["float"] ="double"

        # numeric type conversion depends upon the precision and scale
        dType["numeric"] = "float"  # 4 bytes
        dType["real"] = "double" # 8 bytes

        # Iterate through list of field names and add them to the output table
        i = 0

        # ColumnInfo contains:
        # ColumnOrdinal, ColumnSize, NumericPrecision, NumericScale, ProviderType, IsLong, ProviderSpecificDataType, DataTypeName
        #PrintMsg(" \nFieldName, Length, Precision, Scale, Type", 1)

        joinedFields = list() # new fields that need to be added to the output table
        dataFields = list()   # fields that need to be updated in the AttributeRequest function
        outputTbl = os.path.join("IN_MEMORY", "Template")
        #arcpy.CreateTable_management(os.path.dirname(outputTbl), os.path.basename(outputTbl))

        # Get a list of fields that already exist in outputShp
        outFields = arcpy.Describe(outputShp).fields
        existingFields = [fld.name.lower() for fld in outFields]


        # Using JoinField to add the NATMUSYM column to the outputTbl (but not the data)
        #
        for i, fldName in enumerate(columnNames):
            # Get new field definition from columnInfo dictionary
            vals = columnInfo[i].split(",")
            length = int(vals[1].split("=")[1])
            precision = int(vals[2].split("=")[1])
            scale = int(vals[3].split("=")[1])
            dataType = dType[vals[4].lower().split("=")[1]]

            #if not fldName.lower() == "mukey":
            #    joinedFields.append(fldName)

            if not fldName.lower() in existingFields:
                # This is a new data field that needs to be added to the output table.
                #arcpy.AddField_management(outputTbl, fldName, dataType, precision, scale, length) # add to IN_MEMORY table
                arcpy.AddField_management(outputShp, fldName, dataType, precision, scale, length) # add direct to featureclass
                joinedFields.append(fldName)
                dataFields.append(fldName)

            elif fldName.lower() in existingFields and fldName.lower() != "mukey":
                # This is an existing data field in the output table.
                dataFields.append(fldName)

            elif fldName.lower() == "mukey":
                #arcpy.AddField_management(outputTbl, fldName, dataType, precision, scale, length)
                pass

        if arcpy.Exists(outputTbl) and len(joinedFields) > 0:
            #PrintMsg(" \nAdded these new fields to " + os.path.basename(outputShp) + ": " + ", ".join(joinedFields), 1)
            #arcpy.JoinField_management(outputShp, "mukey", outputTbl, "mukey", joinedFields) # instead add directly to output featureclass
            arcpy.Delete_management(outputTbl)
            return dataFields

        else:
            #PrintMsg(" \nThese fields already exist in the output table: " + ", ".join(dataFields), 1)
            arcpy.Delete_management(outputTbl)
            return dataFields

    except:
        errorMsg()
        return ["Error"]

## ===================================================================================
def GetSDMInfo(theURL, tblName):
    # TEMPORARY CODE
    #
    # POST REST which uses urllib and JSON
    #
    # Send query to SDM Tabular Service, returning data in JSON format

    try:
        if theURL == "":
            theURL = "https://sdmdataaccess.sc.egov.usda.gov"

        sQuery = """SELECT TOP 1 * FROM """ + tblName

        #PrintMsg(" \nRequesting tabular data for " + Number_Format(len(keyList), 0, True) + " soil survey areas...")
        arcpy.SetProgressorLabel("Sending tabular request for " + tblName + " to Soil Data Access...")

        # Tabular service to append to SDA URL
        url = theURL + "/Tabular/SDMTabularService/post.rest"
        dRequest = dict()
        dRequest["format"] = "JSON+COLUMNNAME+METADATA"
        dRequest["query"] = sQuery

        #PrintMsg(" \nURL: " + url)
        #PrintMsg("FORMAT: " + dRequest["FORMAT"])
        #PrintMsg("QUERY: " + sQuery)

        # Create SDM connection to service using HTTP
        jData = json.dumps(dRequest)

        # Send request to SDA Tabular service
        req = urllib2.Request(url, jData)
        resp = urllib2.urlopen(req)

        #PrintMsg(" \nImporting attribute data...", 0)
        #PrintMsg(" \nGot back requested data...", 0)

        # Read the response from SDA into a string
        jsonString = resp.read()

        #PrintMsg(" \njsonString: " + str(jsonString), 1)
        data = json.loads(jsonString)
        del jsonString, resp, req

        if not "Table" in data:
            raise MyError, "Query failed to select anything: \n " + sQuery

        dataList = data["Table"]     # Data as a list of lists. Service returns everything as string.
        arcpy.SetProgressorLabel("Adding new fields to output table...")
        PrintMsg(" \nRequested data consists of " + Number_Format(len(dataList), 0, True) + " records", 0)

        # Get column metadata from first two records
        columnNames = dataList.pop(0)
        columnInfo = dataList.pop(0)

        if len(noMatch) > 0:
            PrintMsg(" \nNo attribute data for mukeys: " + str(noMatch), 1)

        arcpy.SetProgressorLabel("Finished importing attribute data")
        PrintMsg(" \nImport complete... \n ", 0)

        return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except urllib2.HTTPError:
        errorMsg()
        PrintMsg(" \n" + sQuery, 1)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def SetScratch():
    # try to set scratchWorkspace and scratchGDB if null
    #        SYSTEMDRIVE
    #        APPDATA C:\Users\adolfo.diaz\AppData\Roaming
    #        USERPROFILE C:\Users\adolfo.diaz
    try:
        envVariables = os.environ

        for var, val in envVariables.items():
            PrintMsg("\tSystem: " + str(var) + ": " + str(val), 1)

        environments = arcpy.ListEnvironments()

        # Sort the environment names
        environments.sort()

        for ev in environments:
            # Format and print each environment and its current setting.
            # (The environments are accessed by key from arcpy.env.)
            #PrintMsg("{0:<30}: {1}".format(environment, arcpy.env[environment]), 1)
            PrintMsg("\tGP: " + ev + "\t" + str(env[ev]), 1)

        if env.scratchWorkspace is None:
            #PrintMsg("\tWarning. Scratchworkspace has not been set for the geoprocessing environment", 1)
            env.scratchWorkspace = env.scratchFolder
            PrintMsg("\nThe scratch geodatabase has been set to: " + str(env.scratchGDB), 1)

        elif str(env.scratchWorkspace).lower().endswith("default.gdb"):
            PrintMsg("\tChanging scratch geodatabase from Default.gdb", 1)
            env.scratchWorkspace = env.scratchFolder
            PrintMsg("\tTo: " + str(env.scratchGDB), 1)

        #else:
        #    PrintMsg(" \nOriginal Scratch Geodatabase is OK: " + env.scratchGDB, 1)

        if env.scratchGDB:
            return True

        else:
            return False


    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e) + " \n ", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def SetOutputCoordinateSystem(inLayer, AOI):
    #
    # Not being used any more!
    #
    # The GetXML function is now used to set the XML workspace
    # document and a single NAD1983 to WGS1984 datum transformation (ITRF00) is now being used.
    #
    # Below is a description of the 2013 settings
    # Set a hard-coded output coordinate system (Geographic WGS 1984)
    # Set an ESRI datum transformation method for NAD1983 to WGS1984
    # Based upon ESRI 10.1 documentation and the methods that were used to
    # project SDM featureclasses during the transition from ArcSDE to SQL Server spatial
    #
    #   CONUS - NAD_1983_To_WGS_1984_5
    #   Hawaii and American Samoa- NAD_1983_To_WGS_1984_3
    #   Alaska - NAD_1983_To_WGS_1984_5
    #   Puerto Rico and U.S. Virgin Islands - NAD_1983_To_WGS_1984_5
    #   Other  - NAD_1983_To_WGS_1984_1 (shouldn't run into this case)

    try:
        outputSR = arcpy.SpatialReference(4326)        # GCS WGS 1984
        # Get the desired output geographic coordinate system name
        outputGCS = outputSR.GCS.name

        # Describe the input layer and get the input layer's spatial reference, other properties
        desc = arcpy.Describe(inLayer)
        dType = desc.dataType
        sr = desc.spatialReference
        srType = sr.type.upper()
        inputGCS = sr.GCS.name

        # Print name of input layer and dataype
        if dType.upper() == "FEATURELAYER":
            #PrintMsg(" \nInput " + dType + ": " + desc.nameString, 0)
            inputName = desc.nameString

        elif dType.upper() == "FEATURECLASS":
            #PrintMsg(" \nInput " + dType + ": " + desc.baseName, 0)
            inputName = desc.baseName

        else:
            #PrintMsg(" \nInput " + dType + ": " + desc.name, 0)
            inputName = desc.name

        if outputGCS == inputGCS:
            # input and output geographic coordinate systems are the same
            # no datum transformation required
            #PrintMsg(" \nNo datum transformation required", 0)
            tm = ""

        else:
            # Different input and output geographic coordinate systems, set
            # environment to unproject to WGS 1984, matching Soil Data Mart
            tm = "WGS_1984_(ITRF00)_To_NAD_1983"

        # These next two lines set the output coordinate system environment
        arcpy.env.outputCoordinateSystem = outputSR
        arcpy.env.geographicTransformations = tm

        return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CreateSSURGO_DB(outputWS, inputXML, areasymbolList, aliasName):
    # Create new 10.0 File Geodatabase using XML workspace document
    #
    try:
        if not arcpy.Exists(inputXML):
            PrintMsg(" \nMissing input file: " + inputXML, 2)
            return False

        outputFolder = os.path.dirname(outputWS)
        gdbName = os.path.basename(outputWS)

        if arcpy.Exists(os.path.join(outputFolder, gdbName)):
            arcpy.Delete_management(os.path.join(outputFolder, gdbName))

        PrintMsg(" \nCreating new geodatabase (" + gdbName + ") in " + outputFolder, 0)

        env.XYResolution = "0.001 Meters"
        env.XYTolerance = "0.01 Meters"

        arcpy.CreateFileGDB_management(outputFolder, gdbName)

        # The following command will fail when the user only has a Basic license
        arcpy.ImportXMLWorkspaceDocument_management(os.path.join(outputFolder, gdbName), inputXML, "SCHEMA_ONLY")

        # Create indexes for cointerp here.
        # If it works OK, incorporate these indexes into the xml workspace document
        try:
            pass

        except:
            PrintMsg(" \nUnable to index the cointerp table", 1)

        if not arcpy.Exists(os.path.join(outputFolder, gdbName)):
            raise MyError, "Failed to create new geodatabase"

        env.workspace = os.path.join(outputFolder, gdbName)
        tblList = arcpy.ListTables()

        if len(tblList) < 50:
            raise MyError, "Output geodatabase has only " + str(len(tblList)) + " tables"

        # Alter aliases for featureclasses
        if aliasName != "":
            try:
                arcpy.AlterAliasName("MUPOLYGON", "Map Unit Polygons - " + aliasName)
                arcpy.AlterAliasName("MUPOINT", "Map Unit Points - " + aliasName)
                arcpy.AlterAliasName("MULINE", "Map Unit Lines - " + aliasName)
                arcpy.AlterAliasName("FEATPOINT", "Special Feature Points - " + aliasName)
                arcpy.AlterAliasName("FEATLINE", "Special Feature Lines - " + aliasName)
                arcpy.AlterAliasName("SAPOLYGON", "Survey Boundaries - " + aliasName)

            except:
                pass

        arcpy.RefreshCatalog(outputFolder)

        return True

    except MyError, e:
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def GetTableList(outputWS):
    # Query mdstattabs table to get list of input text files (tabular) and output tables
    # This function assumes that the MDSTATTABS table is already present and populated
    # in the output geodatabase per XML Workspace Document.
    #
    # Skip all 'MDSTAT' tables. They are static.
    #
    try:
        tblList = list()
        mdTbl = os.path.join(outputWS, "mdstattabs")

        if not arcpy.Exists(outputWS):
            raise MyError, "Missing output geodatabase: " + outputWS

        if not arcpy.Exists(mdTbl):
            raise MyError, "Missing mdstattabs table in output geodatabase"

        else:
            # got the mdstattabs table, create list
            #mdFields = ('tabphyname','iefilename')
            mdFields = ('tabphyname')

            with arcpy.da.SearchCursor(mdTbl, mdFields) as srcCursor:
                for rec in srcCursor:
                    tblName = rec[0]
                    if not tblName.startswith('mdstat') and not tblName in ('mupolygon', 'muline', 'mupoint', 'featline', 'featpoint', 'sapolygon'):
                        tblList.append(rec[0])

        #PrintMsg(" \nTables to import: " + ", ".join(tblList), 0)
        return tblList

    except MyError, e:
        PrintMsg(str(e), 2)
        return []

    except:
        errorMsg()
        return []

## ===================================================================================
def GetLastDate(inputDB):
    # Get the most recent date 'YYYYMMDD' from SACATALOG.SAVEREST and use it to populate metadata
    #
    try:
        tbl = os.path.join(inputDB, "SACATALOG")
        today = ""
        sqlClause = [None, "ORDER BY SAVEREST DESC"]

        with arcpy.da.SearchCursor(tbl, ['SAVEREST'], sql_clause=sqlClause ) as cur:
            for rec in cur:
                lastDate = rec[0].strftime('%Y%m%d')
                break

        return lastDate


    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return ""

    except:
        errorMsg()
        return ""

## ===================================================================================
def GetTemplateDate(newDB, areaSym):
    # Get SAVEREST date from previously existing Template database
    # Use it to compare with the date from the WSS dataset
    # If the existing database is same or newer, it will be kept and the WSS version skipped.
    # This function is also used to test the output geodatabase to make sure that
    # the tabular import process was successful.
    #
    try:
        if not arcpy.Exists(newDB):
            return 0

        saCatalog = os.path.join(newDB, "SACATALOG")
        dbDate = 0
        whereClause = "UPPER(AREASYMBOL) = '" + areaSym.upper() + "'"
        #PrintMsg(" \nWhereClause for sacatalog: " + areaSym, 1)

        if arcpy.Exists(saCatalog):
            with arcpy.da.SearchCursor(saCatalog, ("SAVEREST"), where_clause=whereClause) as srcCursor:
                for rec in srcCursor:
                    dbDate = str(rec[0]).split(" ")[0]

            del saCatalog
            del newDB
            return dbDate

        else:
            # unable to open SACATALOG table in existing dataset
            return 0

    except:
        errorMsg()
        return 0

## ===================================================================================
def SSURGOVersionTxt(tabularFolder):
    # For future use. Should really create a new table for gSSURGO in order to implement properly.
    #
    # Get SSURGO version from the Template database "SYSTEM Template Database Information" table
    # or from the tabular/version.txt file, depending upon which is being imported.
    # Compare the version number (first digit) to a hardcoded version number which should
    # be theoretically tied to the XML workspace document that accompanies the scripts.

    try:
        # Get SSURGOversion number from version.txt
        versionTxt = os.path.join(tabularFolder, "version.txt")

        if arcpy.Exists(versionTxt):
            # read just the first line of the version.txt file
            fh = open(versionTxt, "r")
            txtVersion = int(fh.readline().split(".")[0])
            fh.close()
            return txtVersion

        else:
            # Unable to compare vesions. Warn user but continue
            PrintMsg("Unable to find tabular file: version.txt", 1)
            return 0

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return 0

    except:
        errorMsg()
        return 0

## ===================================================================================
def SSURGOVersionDB(templateDB):
    # For future use. Should really create a new table for gSSURGO in order to implement properly.
    #
    # Get SSURGO version from the Template database "SYSTEM Template Database Information" table

    try:
        if not arcpy.Exists(templateDB):
            raise MyError, "Missing input database (" + newDB + ")"

        systemInfo = os.path.join(templateDB, "SYSTEM - Template Database Information")

        if arcpy.Exists(systemInfo):
            # Get SSURGO Version from template database
            dbVersion = 0

            with arcpy.da.SearchCursor(systemInfo, "*", "") as srcCursor:
                for rec in srcCursor:
                    if rec[0] == "SSURGO Version":
                        dbVersion = int(str(rec[2]).split(".")[0])
                        #PrintMsg("\tSSURGO Version from DB: " + dbVersion, 1)

            del systemInfo
            del templateDB
            return dbVersion

        else:
            # Unable to open SYSTEM table in existing dataset
            # Warn user but continue
            raise MyError, "Unable to open 'SYSTEM - Template Database Information'"


    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return 0

    except:
        errorMsg()
        return 0

## ===============================================================================================================
def GetTableInfo(newDB):
    # Retrieve physical and alias names from MDSTATTABS table and assigns them to a blank dictionary.
    # Stores physical names (key) and aliases (value) in a Python dictionary i.e. {chasshto:'Horizon AASHTO,chaashto'}
    # Fieldnames are Physical Name = AliasName,IEfilename

    try:
        tblInfo = dict()

        # Open mdstattabs table containing information for other SSURGO tables
        theMDTable = "mdstattabs"
        env.workspace = newDB


        # Establishes a cursor for searching through field rows. A search cursor can be used to retrieve rows.
        # This method will return an enumeration object that will, in turn, hand out row objects
        if arcpy.Exists(os.path.join(newDB, theMDTable)):

            fldNames = ["tabphyname","tablabel","iefilename"]
            with arcpy.da.SearchCursor(os.path.join(newDB, theMDTable), fldNames) as rows:

                for row in rows:
                    # read each table record and assign 'tabphyname' and 'tablabel' to 2 variables
                    physicalName = row[0]
                    aliasName = row[1]
                    importFileName = row[2]

                    if not importFileName in tblInfo:
                        #PrintMsg("\t" + importFileName + ": " + physicalName, 1)
                        tblInfo[importFileName] = physicalName, aliasName

            del theMDTable

            return tblInfo

        else:
            # The mdstattabs table was not found
            raise MyError, "Missing mdstattabs table"
            return tblInfo

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return dict()

## ===================================================================================
def ImportMDTables(newDB, dbList):
    # Import as single set of metadata tables from first survey area's Access database
    # These tables contain table information, relationship classes and domain values
    # They have to be populated before any of the other tables
    #
    # mdstatdomdet
    # mdstatdommas
    # mdstatidxdet
    # mdstatidxmas
    # mdstatrshipdet
    # mdstatrshipmas
    # mdstattabcols
    # mdstattabs

    try:
        #PrintMsg(" \nImporting metadata tables from " + tabularFolder, 1)

        # Create list of tables to be imported
        tables = ['mdstatdommas', 'mdstatidxdet', 'mdstatidxmas', 'mdstatrshipdet', 'mdstatrshipmas', 'mdstattabcols', 'mdstattabs', 'mdstatdomdet']

        accessDB = dbList[0] # source database for metadata table data

        # Process list of text files
        #
        for table in tables:
            arcpy.SetProgressorLabel("Importing " + table + "...")
            inTbl = os.path.join(accessDB, table)
            outTbl = os.path.join(newDB, table)

            if arcpy.Exists(inTbl) and arcpy.Exists(outTbl):
                # Create cursor for all fields to populate the current table
                #
                # For a geodatabase, I need to remove OBJECTID from the fields list
                fldList = arcpy.Describe(outTbl).fields
                fldNames = list()
                fldLengths = list()

                for fld in fldList:
                    if fld.type != "OID":
                        fldNames.append(fld.name.lower())

                        if fld.type.lower() == "string":
                            fldLengths.append(fld.length)

                        else:
                            fldLengths.append(0)

                if len(fldNames) == 0:
                    raise MyError, "Failed to get field names for " + tbl

                with arcpy.da.InsertCursor(outTbl, fldNames) as outcur:
                    incur = arcpy.da.SearchCursor(inTbl, fldNames)
                    # counter for current record number
                    iRows = 0

                    #try:
                    # Use csv reader to read each line in the text file
                    for row in incur:
                        # replace all blank values with 'None' so that the values are properly inserted
                        # into integer values otherwise insertRow fails
                        # truncate all string values that will not fit in the target field
                        newRow = list()
                        fldNo = 0

                        for val in row:  # mdstatdomdet was having problems with this 'for' loop. No idea why.
                            fldLen = fldLengths[fldNo]

                            if fldLen > 0 and not val is None:
                                val = val[0:fldLen]

                            newRow.append(val)

                            fldNo += 1

                        try:
                            outcur.insertRow(newRow)

                        except:
                            raise MyError, "Error handling line " + Number_Format(iRows, 0, True) + " of " + txtPath

                        iRows += 1

                    if iRows < 63:
                        # the smallest table (msrmas.txt) currently has 63 records.
                        raise MyError, tbl + " has only " + str(iRows) + " records"

            else:
                raise MyError, "Required table '" + tbl + "' not found in " + newDB

        return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def ImportMDTabular(newDB, tabularFolder, codePage):
    # Import a single set of metadata text files from first survey area's tabular
    # These files contain table information, relationship classes and domain values
    # They have tobe populated before any of the other tables
    #
    # mdstatdomdet
    # mdstatdommas
    # mdstatidxdet
    # mdstatidxmas
    # mdstatrshipdet
    # mdstatrshipmas
    # mdstattabcols
    # mdstattabs
    #codePage = 'cp1252'

    try:
        PrintMsg(" \nImporting metadata tables from " + tabularFolder, 0)

        # Create list of text files to be imported
        txtFiles = ['mstabcol', 'msrsdet', 'mstab', 'msrsmas', 'msdommas', 'msidxmas', 'msidxdet',  'msdomdet']

        # Create dictionary containing text filename as key, table physical name as value
        tblInfo = {'mstabcol': 'mdstattabcols', 'msrsdet': 'mdstatrshipdet', 'mstab': 'mdstattabs', 'msrsmas': 'mdstatrshipmas', 'msdommas': 'mdstatdommas', 'msidxmas': 'mdstatidxmas', 'msidxdet': 'mdstatidxdet', 'msdomdet': 'mdstatdomdet'}

        csv.field_size_limit(128000)

        # Process list of text files
        for txtFile in txtFiles:

            # Get table name and alias from dictionary
            if txtFile in tblInfo:
                tbl = tblInfo[txtFile]

            else:
                raise MyError, "Required input textfile '" + txtFile + "' not found in " + tabularFolder

            arcpy.SetProgressorLabel("Importing " + tbl + "...")

            # Full path to SSURGO text file
            txtPath = os.path.join(tabularFolder, txtFile + ".txt")

            # continue import process only if the target table exists

            if arcpy.Exists(tbl):
                # Create cursor for all fields to populate the current table
                #
                # For a geodatabase, I need to remove OBJECTID from the fields list
                fldList = arcpy.Describe(os.path.join(newDB, tbl)).fields
                fldNames = list()
                fldLengths = list()

                for fld in fldList:
                    if fld.type != "OID":
                        fldNames.append(fld.name)

                        if fld.type.lower() == "string":
                            fldLengths.append(fld.length)

                        else:
                            fldLengths.append(0)

                if len(fldNames) == 0:
                    raise MyError, "Failed to get field names for " + tbl

                with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                    # counter for current record number
                    iRows = 1  # input textfile line number

                    if os.path.isfile(txtPath):

                        # Use csv reader to read each line in the text file
                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|'):
                            # , quotechar="'"
                            # replace all blank values with 'None' so that the values are properly inserted
                            # into integer values otherwise insertRow fails
                            # truncate all string values that will not fit in the target field
                            newRow = list()
                            fldNo = 0
                            fixedRow = [x.decode(codePage) for x in rowInFile]  # handle non-utf8 characters
                            #.decode('iso-8859-1').encode('utf8')
                            #fixedRow = [x.decode('iso-8859-1').encode('utf8') for x in rowInFile]
                            #fixedRow = [x.decode('iso-8859-1') for x in rowInFile]

                            for val in fixedRow:  # mdstatdomdet was having problems with this 'for' loop. No idea why.
                                fldLen = fldLengths[fldNo]

                                if val == '':
                                    val = None

                                elif fldLen > 0:
                                    val = val[0:fldLen]

                                newRow.append(val)

                                fldNo += 1

                            try:
                                cursor.insertRow(newRow)

                            except:
                                raise MyError, "Error handling line " + Number_Format(iRows, 0, True) + " of " + txtPath

                            iRows += 1

                        if iRows < 63:
                            # msrmas.txt has the least number of records
                            raise MyError, tbl + " has only " + str(iRows) + " records. Check 'md*.txt' files in tabular folder"

                    else:
                        raise MyError, "Missing tabular data file (" + txtPath + ")"

            else:
                raise MyError, "Required table '" + tbl + "' not found in " + newDB

        return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def ImportTables(outputWS, dbList, dbVersion):
    #
    # Import tables from an Access Template database. Does not require text files, but
    # the Access database must be populated and it must reside in the tabular folder and
    # it must be named 'soil_d_<AREASYMBOL>.mdb'
    # Origin: SSURGO_Convert_to_Geodatabase.py
    # Change: 4 columns exist in the .mdb cointerp table but have been removed from the gSSURGO template databases.

    try:
        tblList = GetTableList(outputWS)

        # Something is slowing up the CONUS gSSURGO database creation at the end of this function. Could it be the
        # relationshipclasses triggering new indexes?
        arcpy.SetProgressorLabel("\tAdding additional relationships for sdv* tables...")
        #arcpy.CreateRelationshipClass_management("sdvattribute", "sdvfolderattribute", "xSdvattribute_Sdvfolderattribute", "SIMPLE", "> SDV Folder Attribute Table", "<  SDV Attribute Table", "NONE", "ONE_TO_MANY", "NONE", "attributekey", "attributekey", "","")
        #PrintMsg("    --> zSdvfolder_Sdvfolderattribute", 1)
        #arcpy.CreateRelationshipClass_management("sdvfolder", "sdvfolderattribute", "xSdvfolder_Sdvfolderattribute", "SIMPLE", "> SDV Folder Attribute Table", "<  SDV Folder Table", "NONE", "ONE_TO_MANY", "NONE", "folderkey", "folderkey", "","")


        if len(tblList) == 0:
            raise MyError, "No tables found in " +  outputWS

        # Set up enforcement of unique keys for SDV tables
        #
        dIndex = dict()  # dictionary storing field index for primary key of each SDV table
        dKeys = dict()  # dictionary containing a list of key values for each SDV table
        dFields = dict() # dictionary containing list of fields for eacha SDV table

        keyIndx = dict()  # dictionary containing key field index number for each SDV table
        keyFields = dict() # dictionary containing a list of key field names for each SDV table
        keyFields['sdvfolderattribute'] = "attributekey"
        keyFields['sdvattribute'] = "attributekey"
        keyFields['sdvfolder'] = "folderkey"
        keyFields['sdvalgorithm'] = "algorithmsequence"
        sdvTables = ['sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm']

        for sdvTbl in sdvTables:

            keyField = keyFields[sdvTbl]

            fldList = arcpy.Describe(os.path.join(outputWS, sdvTbl)).fields
            fldNames = list()

            for fld in fldList:
                if fld.type != "OID":
                    fldNames.append(fld.name.lower())

            #dFields[sdvTbl] = fldNames                 # store list of fields for this SDV table
            dIndex[sdvTbl] = fldNames.index(keyField)  # store field index for primary key in this SDV table
            dKeys[sdvTbl] = []                         # initialize key values list for this SDV table

        # End of enforce unique keys setup...


        PrintMsg(" \nImporting tabular data from SSURGO Template databases...", 0)
        iCntr = 0

        for inputDB in dbList:
            iCntr += 1

            # Check SSURGO version in the Template database and make sure it matches this script
            ssurgoVersion = SSURGOVersionDB(inputDB)

            if ssurgoVersion <> dbVersion:
                raise MyError, "Tabular data in " + inputDB + " (SSURGO Version " + str(ssurgoVersion) + ") is not supported"

            # Check the input Template database to make sure it contains data from the Import process
            # Really only checking last record (normally only one record in table). Multiple surveys would fail.
            saCatalog = os.path.join(inputDB, "SACATALOG")

            if arcpy.Exists(saCatalog):
                # parse Areasymbol from database name. If the geospatial naming convention isn't followed,
                # then this will not work.
                fnAreasymbol = inputDB[-9:][0:5].upper()
                dbAreaSymbol = ""

                with arcpy.da.SearchCursor(saCatalog, ("AREASYMBOL")) as srcCursor:
                    for rec in srcCursor:
                        # Get Areasymbol from SACATALOG table, assuming just one survey is present in the database
                        dbAreaSymbol = rec[0]

                if dbAreaSymbol != fnAreasymbol:
                    if dbAreaSymbol != "":
                        raise MyError, "Survey data in " + os.path.basename(inputDB) + " does not match filename"

                    else:
                        raise MyError, "Unable to get survey area information from " + os.path.basename(inputDB)

            else:
                # unable to open SACATALOG table in existing dataset
                # return False which will result in the existing dataset being overwritten by a new WSS download
                PrintMsg("SACATALOG table not found in " + os.path.basename(inputDB), 2)
                return False

            arcpy.SetProgressor("step", "Importing " +  dbAreaSymbol + " tabular data (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(tblList), 0, True) + ")", 0, (len(tblList)) + 1, 1)

            for tblName in tblList:
                outputTbl = os.path.join(outputWS, tblName)
                inputTbl = os.path.join(inputDB, tblName)

                if arcpy.Exists(inputTbl):
                    if tblName != "month" or (tblName == "month" and int(arcpy.GetCount_management(outputTbl).getOutput(0)) < 12):
                        arcpy.SetProgressorLabel("Importing " +  dbAreaSymbol + " tabular data (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + ") : " + tblName)

                        if tblName == 'cointerp':
                            # skipping 4 of the cointerp fields not being used by SDV
                            mdbFieldNames = ['cokey', 'mrulekey', 'mrulename', 'seqnum', 'rulekey', 'rulename', 'ruledepth', 'interphr', 'interphrc', 'nullpropdatabool', 'defpropdatabool', 'incpropdatabool', 'cointerpkey']

                        else:
                            mdbFields = arcpy.Describe(inputTbl).fields
                            mdbFieldNames = list()

                            for inFld in mdbFields:
                                if not inFld.type == "OID":
                                    mdbFieldNames.append(inFld.name.upper())

                        if not tblName in sdvTables:
                            # Import all tables except SDV*

                            with arcpy.da.SearchCursor(inputTbl, mdbFieldNames) as inCursor:
                                #outFields = inCursor.fields

                                with arcpy.da.InsertCursor(outputTbl, mdbFieldNames) as outCursor:
                                    for inRow in inCursor:
                                        outCursor.insertRow(inRow)

                        else:
                            # Import SDV tables while enforcing unique key values
                            # 'sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm'
                            #
                            with arcpy.da.SearchCursor(inputTbl, mdbFieldNames) as inCursor:

                                with arcpy.da.InsertCursor(outputTbl, mdbFieldNames) as outCursor:
                                    for inRow in inCursor:
                                        keyVal = inRow[dIndex[tblName]]

                                        if not keyVal in dKeys[tblName]:
                                            dKeys[tblName].append(keyVal)
                                            outCursor.insertRow(inRow)

                            if inputTbl == "sdvattribute":
                                # Check to see if sainterp contains anything that is not in sdvattribute.nasisrulename.
                                # If so, try to get it from os.path.join(os.path.dirname(sys.argv[0]), MissingInterps.gdb)
                                pass

                else:
                    err = "\tMissing input table: " + inputTbl
                    raise MyError, err

                arcpy.SetProgressorPosition()

            arcpy.ResetProgressor()

        # Add attribute index for each SDV table
        PrintMsg(" \nSkipping indexes for sdv tables", 1)

        #for tblName in sdvTables:
        #    arcpy.SetProgressorLabel("\tAdding attribute index for " + tblName)
        #    sdvTbl = os.path.join(outputWS, tblName)
        #    indexName = "Indx_" + tblName
        #    arcpy.AddIndex_management(sdvTbl, keyFields[tblName], indexName)

        #    if tblName == "sdvattribute":
        #        arcpy.AddIndex_management(sdvTbl, "attributename", "Indx_sdvattributename")

        # Add SDV* table relationships. These aren't part of the XML workspace doc as of FY2018 gSSURGO
        # Not normally necessary, but useful for diagnostics
        #PrintMsg("    --> zSdvattribute_Sdvfolderattribute", 1)
        arcpy.SetProgressorLabel("\tRefreshing ArcCatalog listing")
        arcpy.RefreshCatalog(outputWS)

        return True

    except MyError, e:
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False


## ===================================================================================
def ImportTabular(newDB, dbList, dbVersion, codePage):
    # Use csv reader method of importing text files into geodatabase for those
    # that do not have a populated SSURGO database
    #
    # 2015-12-16 Need to eliminate duplicate records in sdv* tables. Also need to index primary keys
    # for each of these tables.
    #
    try:
        # new code from ImportTables
        #codePage = 'cp1252'

        env.workspace = newDB

        tblList = GetTableList(newDB)

        # Create a dictionary with table information
        tblInfo = GetTableInfo(newDB)

        # PrintMsg("\ttblInfo: " + str(tblInfo), 1)

        if len(tblList) == 0:
            raise MyError, "No tables found in " +  newDB

        #arcpy.SetProgressor("step", "Importing tabular data...",  0, len(dbList), 1)
        PrintMsg(" \nImporting tabular data...", 0)

        iCntr = 0
        #csv.field_size_limit(sys.maxsize)
        csv.field_size_limit(512000)

        # Set up enforcement of unique keys for SDV tables
        #
        sdvTables = ['sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm']
        dIndex = dict()  # dictionary storing field index for primary key of each SDV table
        dKeys = dict()  # dictionary containing a list of key values for each SDV table
        dFields = dict() # dictionary containing list of fields for eacha SDV table

        keyIndx = dict()  # dictionary containing key field index number for each SDV table
        keyFields = dict() # dictionary containing a list of key field names for each SDV table
        keyFields['sdvfolderattribute'] = "attributekey"
        keyFields['sdvattribute'] = "attributekey"
        keyFields['sdvfolder'] = "folderkey"
        keyFields['sdvalgorithm'] = "algorithmsequence"

        # Create a list of textfiles to be imported. The import process MUST follow the
        # order in this list in order to maintain referential integrity. This list
        # will need to be updated if the SSURGO data model is changed in the future.
        #
        txtFiles = ["distmd","legend","distimd","distlmd","lareao","ltext","mapunit", \
        "comp","muaggatt","muareao","mucrpyd","mutext","chorizon","ccancov","ccrpyd", \
        "cdfeat","cecoclas","ceplants","cerosnac","cfprod","cgeomord","chydcrit", \
        "cinterp","cmonth", "cpmatgrp", "cpwndbrk","crstrcts","csfrags","ctxfmmin", \
        "ctxmoicl","ctext","ctreestm","ctxfmoth","chaashto","chconsis","chdsuffx", \
        "chfrags","chpores","chstrgrp","chtext","chtexgrp","chunifie","cfprodo","cpmat","csmoist", \
        "cstemp","csmorgc","csmorhpp","csmormr","csmorss","chstr","chtextur", \
        "chtexmod","sacatlog","sainterp","sdvalgorithm","sdvattribute","sdvfolder","sdvfolderattribute"]

        stepCnt = len(txtFiles) + 2  # adding month and featdesc

        for sdvTbl in sdvTables:
            #sdvTbl = os.path.join(outputWS, "sdvfolderattribute")
            #indx = keyIndx[sdvTbl]
            keyField = keyFields[sdvTbl]

            fldList = arcpy.Describe(os.path.join(newDB, sdvTbl)).fields
            fldNames = list()

            for fld in fldList:
                if fld.type != "OID":
                    fldNames.append(fld.name.lower())

            dFields[sdvTbl] = fldNames                 # store list of fields for this SDV table
            dIndex[sdvTbl] = fldNames.index(keyField)  # store field index for primary key in this SDV table
            dKeys[sdvTbl] = []                         # initialize key values list for this SDV table

        arcpy.SetProgressor("step", "Importing tabular data...", 0, stepCnt, 1)

        for txtFile in txtFiles:

            # Get table name and alias from dictionary
            if txtFile in tblInfo:
                tbl, aliasName = tblInfo[txtFile]

                fldList = arcpy.Describe(tbl).fields
                fldNames = list()

                for fld in fldList:
                    if fld.type != "OID":
                        fldNames.append(fld.name)

                if len(fldNames) == 0:
                    raise MyError, "Failed to get field names for " + tbl

                # Open cursor on tbl
                cursor = arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames)

            else:
                raise MyError, "Textfile reference '" + txtFile + "' not found in 'mdstattabs table'"

            for inputDB in dbList:
                iCntr += 1
                newFolder = os.path.dirname(os.path.dirname(inputDB)) # survey dataset folder

                # parse Areasymbol from database name. If the geospatial naming convention isn't followed,
                # then this will not work.
                soilsFolder = os.path.dirname(os.path.dirname(inputDB))

                #fnAreasymbol = soilsFolder[(soilsFolder.rfind("_") + 1):].upper()
                fnAreasymbol = soilsFolder.upper()
                newFolder = os.path.dirname(os.path.dirname(inputDB)) # survey dataset folder

                # Using csv reader to import tabular data from text files...
                tabularFolder = os.path.join(newFolder, "tabular")

                arcpy.SetProgressorLabel("Importing data to  " + tbl + " for " + fnAreasymbol)

                # Static Metadata Table that records the metadata for all columns of all tables
                # that make up the tabular data set.
                mdstattabsTable = os.path.join(env.workspace, "mdstattabs")

                # Full path to SSURGO text file
                txtPath = os.path.join(tabularFolder, txtFile + ".txt")

                if not arcpy.Exists(txtPath):
                    raise MyError, "Missing tabular data file (" + txtPath + ")"

                if not tbl in ['sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm']:
                    # Import all tables except SDV
                    #
                    time.sleep(0.05)  # Occasional write errors

                    if tbl.endswith("text"):
                        # with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                        # counter for current record number
                        iRows = 1  # input textfile line number

                        try:
                            # Use csv reader to read each line in the text file
                            time.sleep(0.1)  # trying to prevent error reading text file

                            for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                # replace all blank values with 'None' so that the values are properly inserted
                                # into integer values otherwise insertRow fails
                                fixedRow = [x.decode(codePage) if x else None for x in rowInFile]  # handle non-utf8 characters
                                #fixedRow = [x if x else None for x in rowInFile]  # figure out which tables have non-utf8 characters
                                cursor.insertRow(fixedRow) #
                                iRows += 1

                        except:
                            PrintMsg(" \n" + str(fixedRow), 1)
                            err = "Error writing line " + Number_Format(iRows, 0, True) + " from " + txtPath
                            raise MyError, err

                    elif tbl == "cointerp":

                        # with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                        # counter for current record number
                        iRows = 1  # input textfile line number

                        try:
                            # Use csv reader to read each line in the text file
                            time.sleep(0.5)  # trying to prevent error reading text file

                            for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                # replace all blank values with 'None' so that the values are properly inserted
                                # into integer values otherwise insertRow fails
                                #fixedRow = [x.decode(codePage) if x else None for x in rowInFile]  # handle non-utf8 characters
                                r1 = rowInFile[0:7]
                                r2 = rowInFile[11:13]
                                r3 = rowInFile[15:19]
                                r1.extend(r2)
                                r1.extend(r3)
                                fixedRow = [x if x else None for x in r1]  # figure out which tables have non-utf8 characters
                                #mrulekey = fixedRow[1]
                                #ruledepth = fixedRow[6]

                                # Steve only includes rule depths of 0 and NCCPI value
                                if (fixedRow[6] == '0') or (fixedRow[1] == '54955'):
                                    # NCCPI or ruledepth zero
                                    # should I make the 54955 a dynamic variable?
                                    cursor.insertRow(fixedRow) # was fixedRow
                                    #PrintMsg("\t" + str(fixedRow[1]) + ";\t" + str(fixedRow[2]) + ";\t" + str(fixedRow[6]), 1)
                                iRows += 1

                        except:
                            #PrintMsg(" \n" + ", ".join(fldNames), 1)
                            PrintMsg(str(fixedRow), 1)
                            err = "Error writing line " + Number_Format(iRows, 0, True) + " from " + txtPath
                            raise MyError, err

                    else:
                         # with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                        # counter for current record number
                        iRows = 1  # input textfile line number

                        try:
                            # Use csv reader to read each line in the text file
                            time.sleep(0.5)  # trying to prevent error reading text file

                            for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                # replace all blank values with 'None' so that the values are properly inserted
                                # into integer values otherwise insertRow fails
                                #fixedRow = [x.decode(codePage) if x else None for x in rowInFile]  # handle non-utf8 characters
                                fixedRow = [x if x else None for x in rowInFile]  # figure out which tables have non-utf8 characters
                                cursor.insertRow(fixedRow) # was fixedRow
                                iRows += 1

                        except:
                            PrintMsg(" \n" + str(fixedRow), 1)
                            err = "Error writing line " + Number_Format(iRows, 0, True) + " from " + txtPath
                            raise MyError, err

                else:
                    # Import SDV tables while enforcing unique key constraints
                    # 'sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm'
                    #
                    # with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                    # counter for current record number
                    iRows = 1

                    try:
                        # Use csv reader to read each line in the text file
                        time.sleep(0.5)  # trying to prevent error reading text file

                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                            newRow = list()
                            fldNo = 0
                            keyVal = int(rowInFile[dIndex[tbl]])

                            if not keyVal in dKeys[tbl]:
                                # write new record to SDV table
                                dKeys[tbl].append(keyVal)
                                newRow = [x if x else None for x in rowInFile]
                                cursor.insertRow(newRow)  # was newRow
                            iRows += 1

                    except:
                        err = "Error importing line " + Number_Format(iRows, 0, True) + " from " + txtPath + " \n " + str(newRow)
                        PrintMsg(err, 1)
                        #errorMsg()
                        raise MyError, "Error writing line " + Number_Format(iRows, 0, True) + " of " + txtPath

            del cursor

            arcpy.SetProgressorPosition()

        # Populate the month table just once (pre-populated in the Access Template database, no text file)
        #
        monthList = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        tbl = os.path.join(newDB, "month")
        arcpy.SetProgressorLabel("Importing data to " + tbl + " table")

        if int(arcpy.GetCount_management(tbl).getOutput(0)) < 12:
            #arcpy.SetProgressorLabel("Importing " +  fnAreasymbol + " tabular  (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + ") :   " + monthTbl)

            with arcpy.da.InsertCursor(tbl, ["monthseq", "monthname"]) as cur:
                for seq, month in enumerate(monthList):
                    rec = [(seq + 1), month]
                    cur.insertRow(rec)

        arcpy.SetProgressorPosition()

        # PrintMsg("\nUpdating feature description table...", 1)
        tbl = "featdesc"
        arcpy.SetProgressorLabel("Importing data to " + tbl + " table")

        for inputDB in dbList:
            iCntr += 1
            #newFolder = os.path.dirname(os.path.dirname(inputDB)) # survey dataset folder

            # parse Areasymbol from database name. If the geospatial naming convention isn't followed,
            # then this will not work.

            soilsFolder = os.path.dirname(os.path.dirname(inputDB))

            if os.path.basename(soilsFolder).find("_") > -1:
                fnAreasymbol = soilsFolder[-5:].upper()
            else:
                fnAreasymbol = os.path.basename(soilsFolder)

            #fnAreasymbol = soilsFolder[(soilsFolder.rfind("_") + 1):].upper() -- AD
            #fnAreasymbol = os.path.basename(soilsFolder)

            newFolder = os.path.dirname(os.path.dirname(inputDB)) # survey dataset folder

            ##        # Check the database to make sure that it completed properly, with at least the
            # SAVEREST date populated in the SACATALOG table. Featdesc is the last table, but not
            # a good test because often it is not populated.
            dbDate = GetTemplateDate(newDB, fnAreasymbol)

            if dbDate == 0:
                # With this error, it would be best to bailout and fix the problem before proceeding
                raise MyError, "Failed to get Template Date for " + fnAreasymbol


            # Import feature description file. Does this file exist in a NASIS-SSURGO download?
            # soilsf_t_al001.txt
            spatialFolder = os.path.join(newFolder, "spatial")
            txtFile ="soilsf_t_" + fnAreasymbol
            txtPath = os.path.join(spatialFolder, txtFile + ".txt")

            if arcpy.Exists(txtPath):
                # For a geodatabase, I need to remove OBJECTID from the fields list
                fldList = arcpy.Describe(tbl).fields
                fldNames = list()
                for fld in fldList:
                    if fld.type != "OID":
                        fldNames.append(fld.name)

                if len(fldNames) == 0:
                    raise MyError, "Failed to get field names for " + tbl

                # Create cursor for all fields to populate the featdesc table
                with arcpy.da.InsertCursor(tbl, fldNames) as cursor:
                    # counter for current record number
                    iRows = 1
                    #arcpy.SetProgressorLabel("Importing " +  fnAreasymbol + "  (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + "):   " + tbl)

                    try:
                        # Use csv reader to read each line in the text file
                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                            # replace all blank values with 'None' so that the values are properly inserted
                            # into integer values otherwise insertRow fails
                            newRow = [None if value == '' else value for value in rowInFile]
                            cursor.insertRow(newRow)
                            iRows += 1

                    except:
                        errorMsg()
                        raise MyError, "Error loading line no. " + Number_Format(iRows, 0, True) + " of " + txtFile + ".txt"

        arcpy.SetProgressorPosition()  # for featdesc table
        time.sleep(1)

        # Set the Progressor to show completed status
        arcpy.ResetProgressor()

        # Check mapunit and sdvattribute tables. Get rid of certain records if there is no data available.
        # iacornsr IS NOT NULL OR nhiforsoigrp IS NOT NULL OR vtsepticsyscl IS NOT NULL

        # 'Soil-Based Residential Wastewater Disposal Ratings (VT)'  [vtsepticsyscl]

        # 'Iowa Corn Suitability Rating CSR2 (IA)'   [iacornsr]

        # 'NH Forest Soil Group'  [nhiforsoigrp]

        # tblIndexes = GetTableIndexes(newDB)  # using mdstatidxdet table

        bCorn = False
        bNHFor = False
        bVTSeptic = False
        wc = "iacornsr IS NOT NULL"
        with arcpy.da.SearchCursor(os.path.join(newDB, "mapunit"), ["OID@"], where_clause=wc) as cur:
            for rec in cur:
                bCorn = True
                break

        wc = "vtsepticsyscl IS NOT NULL"
        with arcpy.da.SearchCursor(os.path.join(newDB, "mapunit"), ["OID@"], where_clause=wc) as cur:
            for rec in cur:
                bVTSeptic = True
                break

        wc = "nhiforsoigrp IS NOT NULL"
        with arcpy.da.SearchCursor(os.path.join(newDB, "mapunit"), ["OID@"], where_clause=wc) as cur:
            for rec in cur:
                bNHFor = True
                break

        if not bCorn:
            # Next open cursor on the sdvattribute table and delete any unneccessary records
            wc = "attributecolumnname = 'iacornsr'"
            with arcpy.da.UpdateCursor(os.path.join(newDB, "sdvattribute"), ["attributecolumnname"], where_clause=wc) as cur:
                for rec in cur:
                    #PrintMsg("\tDeleted row for iacornsr", 1)
                    cur.deleteRow()

        if not bVTSeptic:
            # Next open cursor on the sdvattribute table and delete any unneccessary records
            wc = "attributecolumnname = 'vtsepticsyscl'"
            with arcpy.da.UpdateCursor(os.path.join(newDB, "sdvattribute"), ["attributecolumnname"], where_clause=wc) as cur:
                for rec in cur:
                    #PrintMsg("\tDeleted row for VT septic", 1)
                    cur.deleteRow()

        if not bNHFor:
            # Next open cursor on the sdvattribute table and delete any unneccessary records
            wc = "attributecolumnname = 'nhiforsoigrp'"
            with arcpy.da.UpdateCursor(os.path.join(newDB, "sdvattribute"), ["attributecolumnname"], where_clause=wc) as cur:
                for rec in cur:
                    #PrintMsg("\tDeleted row for NH forest group", 1)
                    cur.deleteRow()

        arcpy.SetProgressorLabel("Adding attribute index for cointerp table")

        try:
            indxName = "Indx_CointerpRulekey"
            indxList = arcpy.ListIndexes(os.path.join(newDB, "cointerp"), indxName)

            if len(indxList) == 0:
                arcpy.SetProgressorLabel("\tAdding attribute index on rulekey for cointerp table")
                # Tried to add this Cointerp index to the XML workspace document, but slowed down data import.
                arcpy.AddIndex_management(os.path.join(newDB, "COINTERP"), "RULEKEY", indxName)
                arcpy.SetProgressorPosition()

        except:
            errorMsg()
            PrintMsg(" \nUnable to create new rulekey index on the cointerp table", 1)

        arcpy.SetProgressorLabel("Tabular import complete")

        return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def ImportTabularBak(newDB, dbList, dbVersion, codePage):
    # Use csv reader method of importing text files into geodatabase for those
    # that do not have a populated SSURGO database
    #
    # 2015-12-16 Need to eliminate duplicate records in sdv* tables. Also need to index primary keys
    # for each of these tables.
    #
    try:
        # new code from ImportTables
        #codePage = 'cp1252'

        tblList = GetTableList(newDB)

        if len(tblList) == 0:
            raise MyError, "No tables found in " +  newDB

        #arcpy.SetProgressor("step", "Importing tabular data...",  0, len(dbList), 1)
        PrintMsg(" \nImporting tabular data...", 0)

        iCntr = 0

        # Set up enforcement of unique keys for SDV tables
        #
        sdvTables = ['sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm']
        dIndex = dict()  # dictionary storing field index for primary key of each SDV table
        dKeys = dict()  # dictionary containing a list of key values for each SDV table
        dFields = dict() # dictionary containing list of fields for eacha SDV table

        keyIndx = dict()  # dictionary containing key field index number for each SDV table
        keyFields = dict() # dictionary containing a list of key field names for each SDV table
        keyFields['sdvfolderattribute'] = "attributekey"
        keyFields['sdvattribute'] = "attributekey"
        keyFields['sdvfolder'] = "folderkey"
        keyFields['sdvalgorithm'] = "algorithmsequence"

        for sdvTbl in sdvTables:
            #sdvTbl = os.path.join(outputWS, "sdvfolderattribute")
            #indx = keyIndx[sdvTbl]
            keyField = keyFields[sdvTbl]

            fldList = arcpy.Describe(os.path.join(newDB, sdvTbl)).fields
            fldNames = list()

            for fld in fldList:
                if fld.type != "OID":
                    fldNames.append(fld.name.lower())

            dFields[sdvTbl] = fldNames                 # store list of fields for this SDV table
            dIndex[sdvTbl] = fldNames.index(keyField)  # store field index for primary key in this SDV table
            dKeys[sdvTbl] = []                         # initialize key values list for this SDV table


        # Add SDV* table relationships. These aren't part of the XML workspace doc as of FY2018 gSSURGO
        # Not normally necessary, but useful for diagnostics

        for inputDB in dbList:
            iCntr += 1
            newFolder = os.path.dirname(os.path.dirname(inputDB)) # survey dataset folder

            # parse Areasymbol from database name. If the geospatial naming convention isn't followed,
            # then this will not work.
            soilsFolder = os.path.dirname(os.path.dirname(inputDB))

            #fnAreasymbol = soilsFolder[(soilsFolder.rfind("_") + 1):].upper()
            fnAreasymbol = soilsFolder.upper()
            newFolder = os.path.dirname(os.path.dirname(inputDB)) # survey dataset folder

            # get database name from file listing in the new folder
            env.workspace = newFolder

            # move to tabular folder
            env.workspace = os.path.join(newFolder, "tabular")

            # Using Adolfo's csv reader method to import tabular data from text files...
            tabularFolder = os.path.join(newFolder, "tabular")

            # if the tabular directory is empty return False
            if len(os.listdir(tabularFolder)) < 1:
                raise MyError, "No text files found in the tabular folder"

            # Make sure that input tabular data has the correct SSURGO version for this script
            ssurgoVersion = SSURGOVersionTxt(tabularFolder)

            if ssurgoVersion <> dbVersion:
                raise MyError, "Tabular data in " + tabularFolder + " (SSURGO Version " + str(ssurgoVersion) + ") is not supported"

            # Create a dictionary with table information
            tblInfo = GetTableInfo(newDB)

            # Create a list of textfiles to be imported. The import process MUST follow the
            # order in this list in order to maintain referential integrity. This list
            # will need to be updated if the SSURGO data model is changed in the future.
            #
            txtFiles = ["distmd","legend","distimd","distlmd","lareao","ltext","mapunit", \
            "comp","muaggatt","muareao","mucrpyd","mutext","chorizon","ccancov","ccrpyd", \
            "cdfeat","cecoclas","ceplants","cerosnac","cfprod","cgeomord","chydcrit", \
            "cinterp","cmonth", "cpmatgrp", "cpwndbrk","crstrcts","csfrags","ctxfmmin", \
            "ctxmoicl","ctext","ctreestm","ctxfmoth","chaashto","chconsis","chdsuffx", \
            "chfrags","chpores","chstrgrp","chtext","chtexgrp","chunifie","cfprodo","cpmat","csmoist", \
            "cstemp","csmorgc","csmorhpp","csmormr","csmorss","chstr","chtextur", \
            "chtexmod","sacatlog","sainterp","sdvalgorithm","sdvattribute","sdvfolder","sdvfolderattribute"]
            # Need to add featdesc import as a separate item (ie. spatial\soilsf_t_al001.txt: featdesc)

            # Static Metadata Table that records the metadata for all columns of all tables
            # that make up the tabular data set.
            mdstattabsTable = os.path.join(env.workspace, "mdstattabs")

            # set progressor object which allows progress information to be passed for every merge complete
            #arcpy.SetProgressor("step", "Importing " +  fnAreasymbol + " tabular  (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + ")" , 0, len(txtFiles) + 1, 1)

            #csv.field_size_limit(sys.maxsize)
            csv.field_size_limit(512000)

            # For cointerp, adjust for missing columns
            #  x = fldNames[0:7]
            #  y = fldNames[12:14]
            #  z = fldNames[16:20]

            # Need to import text files in a specific order or the MS Access database will
            # return an error due to table relationships and key violations
            for txtFile in txtFiles:

                # Get table name and alias from dictionary
                if txtFile in tblInfo:
                    tbl, aliasName = tblInfo[txtFile]

                else:
                    raise MyError, "Textfile reference '" + txtFile + "' not found in 'mdstattabs table'"

                arcpy.SetProgressorLabel("Importing " +  fnAreasymbol + " tabular data  (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + ") :   " + tbl)

                # Full path to SSURGO text file
                txtPath = os.path.join(tabularFolder, txtFile + ".txt")

                # continue if the target table exists
                if arcpy.Exists(tbl):
                    # Create cursor for all fields to populate the current table
                    #
                    # For a geodatabase, I need to remove OBJECTID from the fields list
                    fldList = arcpy.Describe(tbl).fields
                    fldNames = list()
                    #fldLengths = list()

                    for fld in fldList:
                        if fld.type != "OID":
                            fldNames.append(fld.name)

                    if len(fldNames) == 0:
                        raise MyError, "Failed to get field names for " + tbl

                    if not tbl in ['sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm']:
                        # Import all tables except SDV
                        #
                        time.sleep(0.05)  # Occasional write errors

                        if tbl.endswith("text"):
                            with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                                # counter for current record number
                                iRows = 1  # input textfile line number

                                #if os.path.isfile(txtPath):
                                if arcpy.Exists(txtPath):

                                    try:
                                        # Use csv reader to read each line in the text file
                                        time.sleep(0.5)  # trying to prevent error reading text file

                                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                            # replace all blank values with 'None' so that the values are properly inserted
                                            # into integer values otherwise insertRow fails
                                            fixedRow = [x.decode(codePage) if x else None for x in rowInFile]  # handle non-utf8 characters
                                            #fixedRow = [x if x else None for x in rowInFile]  # figure out which tables have non-utf8 characters
                                            cursor.insertRow(fixedRow) # was fixedRow
                                            iRows += 1

                                    except:
                                        PrintMsg(" \n" + str(fixedRow), 1)
                                        err = "Error writing line " + Number_Format(iRows, 0, True) + " from " + txtPath
                                        raise MyError, err

                                else:
                                    raise MyError, "Missing tabular data file (" + txtPath + ")"

                        elif tbl == "cointerp":

                            with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                                # counter for current record number
                                iRows = 1  # input textfile line number

                                #if os.path.isfile(txtPath):
                                if arcpy.Exists(txtPath):

                                    try:
                                        # Use csv reader to read each line in the text file
                                        time.sleep(0.5)  # trying to prevent error reading text file

                                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                            # replace all blank values with 'None' so that the values are properly inserted
                                            # into integer values otherwise insertRow fails
                                            #fixedRow = [x.decode(codePage) if x else None for x in rowInFile]  # handle non-utf8 characters
                                            r1 = rowInFile[0:7]
                                            r2 = rowInFile[11:13]
                                            r3 = rowInFile[15:19]
                                            r1.extend(r2)
                                            r1.extend(r3)
                                            fixedRow = [x if x else None for x in r1]  # figure out which tables have non-utf8 characters
                                            #mrulekey = fixedRow[1]
                                            #ruledepth = fixedRow[6]

                                            if (fixedRow[6] == '0') or (fixedRow[1] == '54955'):
                                                # NCCPI or ruledepth zero
                                                # should I make the 54955 a dynamic variable?
                                                cursor.insertRow(fixedRow) # was fixedRow
                                                #PrintMsg("\t" + str(fixedRow[1]) + ";\t" + str(fixedRow[2]) + ";\t" + str(fixedRow[6]), 1)
                                            iRows += 1

                                    except:
                                        #PrintMsg(" \n" + ", ".join(fldNames), 1)
                                        PrintMsg(str(fixedRow), 1)
                                        err = "Error writing line " + Number_Format(iRows, 0, True) + " from " + txtPath
                                        raise MyError, err

                                else:
                                    raise MyError, "Missing tabular data file (" + txtPath + ")"


                        else:
                            with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                                # counter for current record number
                                iRows = 1  # input textfile line number

                                #if os.path.isfile(txtPath):
                                if arcpy.Exists(txtPath):

                                    try:
                                        # Use csv reader to read each line in the text file
                                        time.sleep(0.5)  # trying to prevent error reading text file

                                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                            # replace all blank values with 'None' so that the values are properly inserted
                                            # into integer values otherwise insertRow fails
                                            #fixedRow = [x.decode(codePage) if x else None for x in rowInFile]  # handle non-utf8 characters
                                            fixedRow = [x if x else None for x in rowInFile]  # figure out which tables have non-utf8 characters
                                            cursor.insertRow(fixedRow) # was fixedRow
                                            iRows += 1

                                    except:
                                        PrintMsg(" \n" + str(fixedRow), 1)
                                        err = "Error writing line " + Number_Format(iRows, 0, True) + " from " + txtPath
                                        raise MyError, err

                                else:
                                    raise MyError, "Missing tabular data file (" + txtPath + ")"

                    else:
                        # Import SDV tables while enforcing unique key constraints
                        # 'sdvfolderattribute', 'sdvattribute', 'sdvfolder', 'sdvalgorithm'
                        #
                        with arcpy.da.InsertCursor(os.path.join(newDB, tbl), fldNames) as cursor:
                            # counter for current record number
                            iRows = 1

                            if os.path.isfile(txtPath):

                                try:
                                    # Use csv reader to read each line in the text file
                                    time.sleep(0.5)  # trying to prevent error reading text file

                                    for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                                        newRow = list()
                                        fldNo = 0
                                        keyVal = int(rowInFile[dIndex[tbl]])

                                        if not keyVal in dKeys[tbl]:
                                            # write new record to SDV table
                                            dKeys[tbl].append(keyVal)
                                            newRow = [x if x else None for x in rowInFile]
                                            cursor.insertRow(newRow)  # was newRow
                                        iRows += 1

                                except:
                                    err = "Error importing line " + Number_Format(iRows, 0, True) + " from " + txtPath + " \n " + str(newRow)
                                    PrintMsg(err, 1)
                                    #errorMsg()
                                    raise MyError, "Error writing line " + Number_Format(iRows, 0, True) + " of " + txtPath

                            else:
                                raise MyError, "Missing tabular data file (" + txtPath + ")"

                    # Check table count
                    # This isn't correct. May need to look at accumulating total table count in a dictionary
                    #if int(arcpy.GetCount_management(os.path.join(newDB, tbl)).getOutput(0)) != iRows:
                    #    raise MyError, tbl + ": Failed to import all " + Number_Format(iRows, 0, True) + " records into "
                    #

                else:
                    raise MyError, "Required table '" + tbl + "' not found in " + newDB

            #arcpy.SetProgressorPosition()


            # Populate the month table (pre-populated in the Access Template database, no text file)
            #
            monthList = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            monthTbl = os.path.join(newDB, "month")

            if int(arcpy.GetCount_management(monthTbl).getOutput(0)) < 12:
                arcpy.SetProgressorLabel("Importing " +  fnAreasymbol + " tabular  (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + ") :   " + monthTbl)

                with arcpy.da.InsertCursor(monthTbl, ["monthseq", "monthname"]) as cur:
                    for seq, month in enumerate(monthList):
                        rec = [(seq + 1), month]
                        cur.insertRow(rec)

            # Import feature description file. Does this file exist in a NASIS-SSURGO download?
            # soilsf_t_al001.txt
            spatialFolder = os.path.join(os.path.dirname(tabularFolder), "spatial")
            txtFile ="soilsf_t_" + fnAreasymbol
            txtPath = os.path.join(spatialFolder, txtFile + ".txt")
            tbl = "featdesc"

            if arcpy.Exists(txtPath):
                # For a geodatabase, I need to remove OBJECTID from the fields list
                fldList = arcpy.Describe(tbl).fields
                fldNames = list()
                for fld in fldList:
                    if fld.type != "OID":
                        fldNames.append(fld.name)

                if len(fldNames) == 0:
                    raise MyError, "Failed to get field names for " + tbl

                # Create cursor for all fields to populate the featdesc table
                with arcpy.da.InsertCursor(tbl, fldNames) as cursor:
                    # counter for current record number
                    iRows = 1
                    arcpy.SetProgressorLabel("Importing " +  fnAreasymbol + "  (" + Number_Format(iCntr, 0, True) + " of " + Number_Format(len(dbList), 0, True) + "):   " + tbl)

                    try:
                        # Use csv reader to read each line in the text file
                        for rowInFile in csv.reader(open(txtPath, 'rb'), delimiter='|', quotechar='"'):
                            # replace all blank values with 'None' so that the values are properly inserted
                            # into integer values otherwise insertRow fails
                            newRow = [None if value == '' else value for value in rowInFile]
                            cursor.insertRow(newRow)
                            iRows += 1

                    except:
                        errorMsg()
                        raise MyError, "Error loading line no. " + Number_Format(iRows, 0, True) + " of " + txtFile + ".txt"

                arcpy.SetProgressorPosition()  # for featdesc table
                time.sleep(1.0)

            #else:
                # featdesc.txt file does not exist. NASIS-SSURGO download:
            #    PrintMsg("\tMissing file " + txtPath, 1)

            # Check the database to make sure that it completed properly, with at least the
            # SAVEREST date populated in the SACATALOG table. Featdesc is the last table, but not
            # a good test because often it is not populated.
            PrintMsg(fnAreasymbol + " -- ImportTabularBak")
            dbDate = GetTemplateDate(newDB, fnAreasymbol)

            if dbDate == 0:
                # With this error, it would be best to bailout and fix the problem before proceeding
                raise MyError, "Failed to get Template Date for " + fnAreasymbol

            # Set the Progressor to show completed status
            arcpy.ResetProgressor()

        # Check mapunit and sdvattribute tables. Get rid of certain records if there is no data available.
        # iacornsr IS NOT NULL OR nhiforsoigrp IS NOT NULL OR vtsepticsyscl IS NOT NULL

        # 'Soil-Based Residential Wastewater Disposal Ratings (VT)'  [vtsepticsyscl]

        # 'Iowa Corn Suitability Rating CSR2 (IA)'   [iacornsr]

        # 'NH Forest Soil Group'  [nhiforsoigrp]

        # tblIndexes = GetTableIndexes(newDB)  # using mdstatidxdet table

        bCorn = False
        bNHFor = False
        bVTSeptic = False
        wc = "iacornsr IS NOT NULL"
        with arcpy.da.SearchCursor(os.path.join(newDB, "mapunit"), ["OID@"], where_clause=wc) as cur:
            for rec in cur:
                bCorn = True
                break

        wc = "vtsepticsyscl IS NOT NULL"
        with arcpy.da.SearchCursor(os.path.join(newDB, "mapunit"), ["OID@"], where_clause=wc) as cur:
            for rec in cur:
                bVTSeptic = True
                break

        wc = "nhiforsoigrp IS NOT NULL"
        with arcpy.da.SearchCursor(os.path.join(newDB, "mapunit"), ["OID@"], where_clause=wc) as cur:
            for rec in cur:
                bNHFor = True
                break

        if not bCorn:
            # Next open cursor on the sdvattribute table and delete any unneccessary records
            wc = "attributecolumnname = 'iacornsr'"
            with arcpy.da.UpdateCursor(os.path.join(newDB, "sdvattribute"), ["attributecolumnname"], where_clause=wc) as cur:
                for rec in cur:
                    #PrintMsg("\tDeleted row for iacornsr", 1)
                    cur.deleteRow()

        if not bVTSeptic:
            # Next open cursor on the sdvattribute table and delete any unneccessary records
            wc = "attributecolumnname = 'vtsepticsyscl'"
            with arcpy.da.UpdateCursor(os.path.join(newDB, "sdvattribute"), ["attributecolumnname"], where_clause=wc) as cur:
                for rec in cur:
                    #PrintMsg("\tDeleted row for VT septic", 1)
                    cur.deleteRow()

        if not bNHFor:
            # Next open cursor on the sdvattribute table and delete any unneccessary records
            wc = "attributecolumnname = 'nhiforsoigrp'"
            with arcpy.da.UpdateCursor(os.path.join(newDB, "sdvattribute"), ["attributecolumnname"], where_clause=wc) as cur:
                for rec in cur:
                    #PrintMsg("\tDeleted row for NH forest group", 1)
                    cur.deleteRow()

        arcpy.SetProgressorLabel("Adding attribute index for cointerp table")

        try:
            indxName = "Indx_CointerpRulekey"
            indxList = arcpy.ListIndexes(os.path.join(newDB, "cointerp"), indxName)

            if len(indxList) == 0:
                arcpy.SetProgressorLabel("\tAdding attribute index on rulekey for cointerp table")
                # Tried to add this Cointerp index to the XML workspace document, but slowed down data import.
                arcpy.AddIndex_management(os.path.join(newDB, "COINTERP"), "RULEKEY", indxName)
                arcpy.SetProgressorPosition()

        except:
            errorMsg()
            PrintMsg(" \nUnable to create new rulekey index on the cointerp table", 1)

        arcpy.SetProgressorLabel("Tabular import complete")

        return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False


## ===================================================================================
def IdentifyNewInterps(outputWS):
    # Generate list of unpublished interps not found in sdvattribute table, but do exist
    # in the sainterp and cointerp tables of this NASIS-SSURGO download
    # Adding this information will help make these interps 'mappable'.
    #
    # In FY2019 we ran into a problem where some of the new interps were exported to sainterp, cointerp, but
    # not added to the sdvattribute table. Identify those so that they can be retrieved from MissingInterps.gdb.

    try:

        sdvInterps = list()
        missingInterps = list()
        missingDB = os.path.join(os.path.dirname(sys.argv[0]), "MissingInterps.gdb")

        if not arcpy.Exists(missingDB):
            raise MyError, "Missing database: " + missingDB

        # create pointers to tables being used
        sainterpTbl = os.path.join(outputWS, "sainterp")
        sdvattTbl = os.path.join(outputWS, "sdvattribute")
        sdvfolderattTbl = os.path.join(outputWS, "sdvfolderattribute")
        sdvfolderTbl = os.path.join(outputWS, "sdvfolder")

        with arcpy.da.SearchCursor(sdvattTbl, ["nasisrulename"], where_clause="attributetablename = 'cointerp'") as cur:
            for rec in cur:
                interpName = rec[0].encode('ascii')

                if not interpName in sdvInterps:
                    sdvInterps.append(interpName)

        with arcpy.da.SearchCursor(sainterpTbl, ["interpname"]) as cur:
            for rec in cur:
                interpName = rec[0].encode('ascii')

                if not interpName in sdvInterps and not interpName in missingInterps:
                    missingInterps.append(interpName)

        for interpName in missingInterps:
            # Get the missing information from MissingInterps.gdb
            srcTbl = os.path.join(missingDB, "sdvattribute")
            sdvattFlds = [fld.name for fld in arcpy.Describe(srcTbl).fields if fld.type != "OID"]
            sdvwc = "nasisrulename = '" + interpName + "'"
            #PrintMsg("\tMissing " + interpName, 1)
            sdvCnt = 0

            with arcpy.da.SearchCursor(os.path.join(missingDB, "sdvattribute"), sdvattFlds, where_clause=sdvwc) as incur:
                for rec in incur:
                    # Insert copy of missing record into gSSURGO database
                    if sdvCnt > 0:
                        raise MyError, "Where_Clause failed to get just one record: " + sdvwc

                    sdvCnt += 1
                    attributeKey = rec[0]

                    with arcpy.da.InsertCursor(sdvattTbl, sdvattFlds) as outcur:
                        outcur.insertRow(rec)

                    folderwc = "attributekey = " + str(attributeKey)
                    folderKey = None

                    with arcpy.da.SearchCursor(os.path.join(missingDB, "sdvfolderattribute"),  ["folderkey"], where_clause=folderwc) as fcur:
                        for frec in fcur:
                            #PrintMsg("\t\tGot folderkey: " + str(frec[0]), 1)
                            folderKey = frec[0]

                    if not folderKey is None and interpName.find("Radioactive") == -1:
                        PrintMsg("\tAdding missing information for interpretation: '" + interpName + "'", 0)

                        with arcpy.da.InsertCursor(sdvfolderattTbl, ["folderkey", "attributekey"]) as outcur:
                            newrec = [folderKey, attributeKey]
                            outcur.insertRow(newrec)


        return True


    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def AppendFeatures(outputWS, AOI, mupolyList, mulineList, mupointList, sflineList, sfpointList, sapolyList, featCnt):
    # Merge all spatial layers into a set of file geodatabase featureclasses
    # Compare shapefile feature count to GDB feature count
    # featCnt:  0 mupoly, 1 muline, 2 mupoint, 3 sfline, 4 sfpoint, 5 sapoly
    try:
        # Set output workspace
        env.workspace = outputWS

        # Put datum transformation methods in place
        #AOI = "CONUS"
        PrintMsg(" \nImporting spatial data...", 0)

        # Problem if soil polygon shapefile has MUNAME column or other alterations
        # Need to use fieldmapping parameter to fix append error.
        fieldmappings = arcpy.FieldMappings()
        fieldmappings.addTable(os.path.join(outputWS, "MUPOLYGON"))
        fieldmappings.addTable(os.path.join(outputWS, "MULINE"))
        fieldmappings.addTable(os.path.join(outputWS, "MUPOINT"))
        fieldmappings.addTable(os.path.join(outputWS, "FEATLINE"))
        fieldmappings.addTable(os.path.join(outputWS, "FEATPOINT"))
        fieldmappings.addTable(os.path.join(outputWS, "SAPOLYGON"))

        # Assuming input featureclasses from Web Soil Survey are GCS WGS1984 and that
        # output datum is either NAD 1983 or WGS 1984. Output coordinate system will be
        # defined by the existing output featureclass.

        # WITH XML workspace method, I need to use Append_management

        # Merge process MUPOLYGON
        if len(mupolyList) > 0:
            PrintMsg(" \n\tAppending " + str(len(mupolyList)) + " soil mapunit polygon shapefiles to create new featureclass: " + "MUPOLYGON", 0)
            arcpy.SetProgressorLabel("Appending features to MUPOLYGON layer")
            arcpy.Append_management(mupolyList,  os.path.join(outputWS, "MUPOLYGON"), "NO_TEST", fieldmappings )
            mupolyCnt = int(arcpy.GetCount_management(os.path.join(outputWS, "MUPOLYGON")).getOutput(0))

            if mupolyCnt != featCnt[0]:
                raise MyError, "MUPOLYGON imported only " + Number_Format(mupolyCnt, 0, True) + " polygons, should be " + Number_Format(featCnt[0], 0, True)
            #PrintMsg(" \nMUPOLYGON imported only " + Number_Format(mupolyCnt, 0, True) + " polygons, should be " + Number_Format(featCnt[0], 0, True), 1)

            # Add spatial index
            arcpy.AddSpatialIndex_management(os.path.join(outputWS, "MUPOLYGON"))
            arcpy.AddIndex_management(os.path.join(outputWS, "MUPOLYGON"), "AREASYMBOL", "Indx_MupolyAreasymbol")

        #PrintMsg(" \nSkipping import for other featureclasses until problem with shapefile primary key is fixed", 0)
        #return True

        # Merge process MULINE
        if len(mulineList) > 0:
            PrintMsg(" \n\tAppending " + str(len(mulineList)) + " soil mapunit line shapefiles to create new featureclass: " + "MULINE", 0)
            arcpy.SetProgressorLabel("Appending features to MULINE layer")
            arcpy.Append_management(mulineList,  os.path.join(outputWS, "MULINE"), "NO_TEST", fieldmappings)
            mulineCnt = int(arcpy.GetCount_management(os.path.join(outputWS, "MULINE")).getOutput(0))

            if mulineCnt != featCnt[1]:
                raise MyError, "MULINE short count"

            # Add spatial index
            arcpy.AddSpatialIndex_management(os.path.join(outputWS, "MULINE"))

            # Add attribute indexes
            arcpy.AddIndex_management(os.path.join(outputWS, "MULINE"), "AREASYMBOL", "Indx_MulineAreasymbol")

        # Merge process MUPOINT
        if len(mupointList) > 0:
            PrintMsg(" \n\tAppending " + str(len(mupointList)) + " soil mapunit point shapefiles to create new featureclass: " + "MUPOINT", 0)
            arcpy.SetProgressorLabel("Appending features to MUPOINT layer")
            arcpy.Append_management(mupointList,  os.path.join(outputWS, "MUPOINT"), "NO_TEST", fieldmappings)
            mupointCnt = int(arcpy.GetCount_management(os.path.join(outputWS, "MUPOINT")).getOutput(0))

            if mupointCnt != featCnt[2]:
                raise MyError, "MUPOINT short count"

            # Add spatial index
            arcpy.AddSpatialIndex_management(os.path.join(outputWS, "MUPOINT"))

            # Add attribute indexes
            arcpy.AddIndex_management(os.path.join(outputWS, "MUPOINT"), "AREASYMBOL", "Indx_MupointAreasymbol")

        # Merge process FEATLINE
        if len(sflineList) > 0:
            PrintMsg(" \n\tAppending " + str(len(sflineList)) + " special feature line shapefiles to create new featureclass: " + "FEATLINE", 0)
            arcpy.SetProgressorLabel("Appending features to FEATLINE layer")
            arcpy.Append_management(sflineList,  os.path.join(outputWS, "FEATLINE"), "NO_TEST", fieldmappings)
            sflineCnt = int(arcpy.GetCount_management(os.path.join(outputWS, "FEATLINE")).getOutput(0))

            if sflineCnt != featCnt[3]:
                raise MyError, "FEATLINE short count"

            # Add spatial index -- This errors out with CONUS dataset.
            try:
                arcpy.AddSpatialIndex_management(os.path.join(outputWS, "FEATLINE"))
            except:
                pass

            # Add attribute indexes
            arcpy.AddIndex_management(os.path.join(outputWS, "FEATLINE"), "AREASYMBOL", "Indx_SFLineAreasymbol")

        # Merge process FEATPOINT
        if len(sfpointList) > 0:
            PrintMsg(" \n\tAppending " + str(len(sfpointList)) + " special feature point shapefiles to create new featureclass: " + "FEATPOINT", 0)
            arcpy.SetProgressorLabel("Appending features to FEATPOINT layer")
            arcpy.Append_management(sfpointList,  os.path.join(outputWS, "FEATPOINT"), "NO_TEST", fieldmappings)
            sfpointCnt = int(arcpy.GetCount_management(os.path.join(outputWS, "FEATPOINT")).getOutput(0))

            if sfpointCnt != featCnt[4]:
                PrintMsg(" \nWA619 SF Points had 3136 in the original shapefile", 1)
                PrintMsg("featCnt is " + str(featCnt[4]), 1)
                PrintMsg(" \nExported " + str(sfpointCnt) + " points to geodatabase", 1)
                raise MyError, "FEATPOINT short count"

            # Add spatial index
            arcpy.AddSpatialIndex_management(os.path.join(outputWS, "FEATPOINT"))

            # Add attribute indexes
            arcpy.AddIndex_management(os.path.join(outputWS, "FEATPOINT"), "AREASYMBOL", "Indx_SFPointAreasymbol")

        # Merge process SAPOLYGON
        if len(sapolyList) > 0:
            PrintMsg(" \n\tAppending " + str(len(sapolyList)) + " survey boundary shapefiles to create new featureclass: " + "SAPOLYGON", 0)
            arcpy.SetProgressorLabel("Appending features to SAPOLYGON layer")
            arcpy.Append_management(sapolyList,  os.path.join(outputWS, "SAPOLYGON"), "NO_TEST", fieldmappings)
            sapolyCnt = int(arcpy.GetCount_management(os.path.join(outputWS, "SAPOLYGON")).getOutput(0))

            if sapolyCnt != featCnt[5]:
                raise MyError, "SAPOLYGON short count"

            # Add spatial index
            arcpy.AddSpatialIndex_management(os.path.join(outputWS, "SAPOLYGON"))


        arcpy.RefreshCatalog(outputWS)

        if not arcpy.Exists(outputWS):
            raise MyError, outputWS + " not found at end of AppendFeatures..."

        return True

    except MyError, e:
        PrintMsg(str(e), 2)

    except:
        errorMsg()
        return False

## ===================================================================================
def StateNames():
    # Create dictionary object containing list of state abbreviations and their names that
    # will be used to name the file geodatabase.
    # For some areas such as Puerto Rico, U.S. Virgin Islands, Pacific Islands Area the
    # abbrevation is

    # NEED TO UPDATE THIS FUNCTION TO USE THE LAOVERLAP TABLE AREANAME. AREASYMBOL IS STATE ABBREV

    try:
        stDict = dict()
        stDict["AL"] = "Alabama"
        stDict["AK"] = "Alaska"
        stDict["AS"] = "American Samoa"
        stDict["AZ"] = "Arizona"
        stDict["AR"] = "Arkansas"
        stDict["CA"] = "California"
        stDict["CO"] = "Colorado"
        stDict["CT"] = "Connecticut"
        stDict["DC"] = "District of Columbia"
        stDict["DE"] = "Delaware"
        stDict["FL"] = "Florida"
        stDict["GA"] = "Georgia"
        stDict["HI"] = "Hawaii"
        stDict["ID"] = "Idaho"
        stDict["IL"] = "Illinois"
        stDict["IN"] = "Indiana"
        stDict["IA"] = "Iowa"
        stDict["KS"] = "Kansas"
        stDict["KY"] = "Kentucky"
        stDict["LA"] = "Louisiana"
        stDict["ME"] = "Maine"
        stDict["MD"] = "Maryland"
        stDict["MA"] = "Massachusetts"
        stDict["MI"] = "Michigan"
        stDict["MN"] = "Minnesota"
        stDict["MS"] = "Mississippi"
        stDict["MO"] = "Missouri"
        stDict["MT"] = "Montana"
        stDict["NE"] = "Nebraska"
        stDict["NV"] = "Nevada"
        stDict["NH"] = "New Hampshire"
        stDict["NJ"] = "New Jersey"
        stDict["NM"] = "New Mexico"
        stDict["NY"] = "New York"
        stDict["NC"] = "North Carolina"
        stDict["ND"] = "North Dakota"
        stDict["OH"] = "Ohio"
        stDict["OK"] = "Oklahoma"
        stDict["OR"] = "Oregon"
        stDict["PA"] = "Pennsylvania"
        stDict["PRUSVI"] = "Puerto Rico and U.S. Virgin Islands"
        stDict["RI"] = "Rhode Island"
        stDict["Sc"] = "South Carolina"
        stDict["SD"] ="South Dakota"
        stDict["TN"] = "Tennessee"
        stDict["TX"] = "Texas"
        stDict["UT"] = "Utah"
        stDict["VT"] = "Vermont"
        stDict["VA"] = "Virginia"
        stDict["WA"] = "Washington"
        stDict["WV"] = "West Virginia"
        stDict["WI"] = "Wisconsin"
        stDict["WY"] = "Wyoming"
        return stDict

    except:
        PrintMsg("\tFailed to create list of state abbreviations (CreateStateList)", 2)
        return stDict

## ===================================================================================
def GetXML(AOI):
    # Set appropriate XML Workspace Document according to AOI
    # The xml files referenced in this function must all be stored in the same folder as the
    # Python script and toolbox
    #
    # FY2016. Discovered that my MD* tables in the XML workspace documents were out of date.
    # Need to update and figure out a way to keep them updated
    #
    try:
        # Set folder path for workspace document (same as script)
        xmlPath = os.path.dirname(sys.argv[0])

        # Changed datum transformation to use ITRF00 for ArcGIS 10.1
        # FYI. Multiple geographicTransformations would require a semi-colon delimited string
        tm = "WGS_1984_(ITRF00)_To_NAD_1983"

        # Input XML workspace document used to create new gSSURGO schema in an empty geodatabase
        if AOI == "Lower 48 States":
            #inputXML = os.path.join(xmlPath, "gSSURGO_CONUS_AlbersNAD1983.xml")
            #PrintMsg(" \nUsing test xmlworkspacedocument for CONUS", 1)
            #inputXML = os.path.join(xmlPath, "gSSURGO_CONUS_AlbersNAD1983.xml")
            #inputXML = os.path.join(xmlPath, "gSSURGO_CONUS_AlbersNAD1983.xml")
            inputXML = os.path.join(xmlPath, "gSSURGO_CONUS_5070.xml")
            tm = "WGS_1984_(ITRF00)_To_NAD_1983"

        elif AOI == "Hawaii":
            #inputXML = os.path.join(xmlPath, "gSSURGO_Hawaii_AlbersWGS1984.xml")
            inputXML = os.path.join(xmlPath, "gSSURGO_4326.xml")
            tm = ""

        elif AOI == "American Samoa":
            #inputXML = os.path.join(xmlPath, "gSSURGO_Hawaii_AlbersWGS1984.xml")
            inputXML = os.path.join(xmlPath, "gSSURGO_4326.xml")
            tm = ""

        elif AOI == "Alaska":
            #inputXML = os.path.join(xmlPath, "gSSURGO_Alaska_AlbersWGS1984.xml")
            inputXML = os.path.join(xmlPath, "gSSURGO_Alaska_3338.xml")
            tm = ""

        elif AOI == "Puerto Rico and U.S. Virgin Islands":
            #inputXML = os.path.join(xmlPath, "gSSURGO_CONUS_AlbersNAD1983.xml")
            inputXML = os.path.join(xmlPath, "gSSURGO_PRUSVI_32161.xml")
            tm = "WGS_1984_(ITRF00)_To_NAD_1983"

        elif AOI == "Pacific Islands Area":
            #inputXML = os.path.join(xmlPath, "gSSURGO_PACBasin_AlbersWGS1984.xml")
            inputXML = os.path.join(xmlPath, "gSSURGO_4326.xml")
            # No datum transformation required for PAC Basin data
            tm = ""

        elif AOI == "World":
            PrintMsg(" \nOutput coordinate system will be Geographic WGS 1984", 0)
            inputXML = os.path.join(xmlPath, "gSSURGO_Geographic_WGS1984.xml")
            tm = ""

        else:
            PrintMsg(" \nNo projection is being applied", 1)
            inputXML = os.path.join(xmlPath, "gSSURGO_GCS_WGS1984.xml")
            tm = ""

        arcpy.env.geographicTransformations = tm

        return inputXML

    except:
        errorMsg()
        return ""

## ===================================================================================
def UpdateMetadata(outputWS, target, surveyInfo, description):
    #
    # Used for featureclass and geodatabase metadata. Does not do individual tables
    # Reads and edits the original metadata object and then exports the edited version
    # back to the featureclass or database.
    #
    # Several times over the years I've had problems with ExportMetadata errors:
    # ERROR 000584: Implementation of this Tool's Validate is invalid.
    # I now believe this occurs when the geoprocessing workspace environments point to
    # folder or geodatabases that don't exist. The folder was somehow deleted.
    #
    try:
        if outputWS == target:
            # Updating the geodatabase metadata
            #target = outputWS
            PrintMsg("\tGeodatabase", 0)

        else:
            # Updating featureclass metadata
            target = os.path.join(outputWS, target)
            PrintMsg("\t" + os.path.basename(target.title()), 0)

        # Set metadata translator file
        dInstall = arcpy.GetInstallInfo()
        installPath = dInstall["InstallDir"]
        prod = r"Metadata/Translator/ARCGIS2FGDC.xml"
        #prod = r"Metadata/Translator/ArcGIS2ISO19139.xml"
        mdTranslator = os.path.join(installPath, prod)

        if not arcpy.Exists(mdTranslator):
            raise MyError, "Missing metadata translator file (" + mdTranslator + ")"

        # Define input and output XML files
        env.scratchFolder
        env.scratchGDB
        mdExport = os.path.join(env.scratchFolder, "xxExport.xml")  # initial metadata exported from current MUPOLYGON featureclass
        mdImport = os.path.join(env.scratchFolder, "xxImport.xml")  # the metadata xml that will provide the updated info

        # Cleanup XML files from previous runs
        if os.path.isfile(mdImport):
            os.remove(mdImport)

        if os.path.isfile(mdExport):
            os.remove(mdExport)

        #PrintMsg(" \nExporting metadata from " + target, 1)
        #PrintMsg("Current workspace is " + env.workspace, 1)

        arcpy.ExportMetadata_conversion(target, mdTranslator, mdExport)

        # Get replacement value for the search words
        #
        stDict = StateNames()
        st = os.path.basename(outputWS)[8:-4]

        if st in stDict:
            # Get state name from the geodatabase
            mdState = stDict[st]

        else:
            # Use description as state name
            #mdState = st
            mdState = description

        # Set date strings for metadata, based upon today's date
        #
        d = datetime.date.today()
        #today = str(d.isoformat().replace("-",""))

        lastDate = GetLastDate(outputWS)

        # Set fiscal year according to the current month. If run during January thru September,
        # set it to the current calendar year. Otherwise set it to the next calendar year.
        #
##        if d.month > 9:
##            fy = "FY" + str(d.year + 1)
##
##        else:
##            fy = "FY" + str(d.year)
##
##        if d.month > 9:
##            fy = "FY" + str(d.year + 1)
##
##        else:
##            fy = "FY" + str(d.year)

        # As of July 2020, switch gSSURGO version format to YYYYMM
        fy = d.strftime('%Y%m')

        # Parse exported XML metadata file
        #
        # Convert XML to tree format
        tree = ET.parse(mdExport)
        root = tree.getroot()

        # new citeInfo has title.text, edition.text, serinfo/issue.text
        citeInfo = root.findall('idinfo/citation/citeinfo/')

        if not citeInfo is None:
            # Process citation elements
            # title
            #
            # PrintMsg("citeInfo with " + str(len(citeInfo)) + " elements : " + str(citeInfo), 1)
            for child in citeInfo:
                #PrintMsg("\t\t" + str(child.tag), 0)
                if child.tag == "title":
                    if child.text.find('xxSTATExx') >= 0:
                        child.text = child.text.replace('xxSTATExx', mdState)

                    elif mdState != "":
                        child.text = child.text + " - " + mdState

                elif child.tag == "edition":
                    if child.text == 'xxFYxx':
                        child.text = fy

                elif child.tag == "serinfo":
                    for subchild in child.iter('issue'):
                        if subchild.text == "xxFYxx":
                            subchild.text = fy

        # Update place keywords
        #PrintMsg("\t\tplace keywords", 0)
        ePlace = root.find('idinfo/keywords/place')

        for child in ePlace.iter('placekey'):
            if child.text == "xxSTATExx":
                child.text = mdState

            elif child.text == "xxSURVEYSxx":
                child.text = surveyInfo

        # Update credits
        eIdInfo = root.find('idinfo')
        #PrintMsg("\t\tcredits", 0)

        for child in eIdInfo.iter('datacred'):
            sCreds = child.text

            if sCreds.find("xxSTATExx") >= 0:
                #PrintMsg("\t\tcredits " + mdState, 0)
                child.text = child.text.replace("xxSTATExx", mdState)

            if sCreds.find("xxFYxx") >= 0:
                #PrintMsg("\t\tcredits " + fy, 0)
                child.text = child.text.replace("xxFYxx", fy)

            if sCreds.find("xxTODAYxx") >= 0:
                #PrintMsg("\t\tcredits " + today, 0)
                child.text = child.text.replace("xxTODAYxx", lastDate)

        idPurpose = root.find('idinfo/descript/purpose')
        if not idPurpose is None:
            ip = idPurpose.text
            #PrintMsg("\tip: " + ip, 1)
            if ip.find("xxFYxx") >= 0:
                #PrintMsg("\t\tip", 1)
                idPurpose.text = ip.replace("xxFYxx", fy)

        procDates = root.find('dataqual/lineage')
        if not procDates is None:
            #PrintMsg(" \nUpdating process step dates", 1)
            for child in procDates.iter('procdate'):

                sDate = child.text
                #PrintMsg("\tFound process date: " + sDate, 1)
                if sDate.find('xxTODAYxx'):
                    #PrintMsg("\tReplacing process date: " + sDate + " with " + lastDate, 1)
                    child.text = lastDate

        else:
            PrintMsg("\nNo find process date", 1)

        #  create new xml file which will be imported, thereby updating the table's metadata
        tree.write(mdImport, encoding="utf-8", xml_declaration=None, default_namespace=None, method="xml")

        # import updated metadata to the geodatabase table
        arcpy.ImportMetadata_conversion(mdImport, "FROM_FGDC", target, "DISABLED")

        # Clear geoprocessing history from the target metadata
        out_xml = os.path.join(env.scratchFolder, "xxClean.xml")

        if arcpy.Exists(out_xml):
            arcpy.Delete_management(out_xml)
            #PrintMsg(" \nKeeping metadata file " + out_xml, 1)

        #arcpy.XSLTransform_conversion(target, remove_gp_history_xslt, out_xml, "")
        #arcpy.MetadataImporter_conversion(out_xml, target)

        # delete the temporary xml metadata files
        if os.path.isfile(mdImport):
            os.remove(mdImport)
            #PrintMsg(" \nKeeping temporary medatafiles: " + mdImport, 1)
            #pass

        if os.path.isfile(mdExport):
            os.remove(mdExport)
            #pass
            #PrintMsg(" \nKeeping temporary medatafiles: " + mdExport, 1)
            #time.sleep(5)

        if arcpy.Exists(out_xml):
            arcpy.Delete_management(out_xml)

        del target

        return True

    except:
        errorMsg()
        False

## ===================================================================================
def gSSURGO(inputFolder, surveyList, outputWS, AOI, tileInfo, useTextFiles, bClipped, areasymbolList):
    # main function
    # inputFolder = main folder that contains all WSS downloads
    # surveyList = list of WSS folders i.e. [u'soil_de001', u'soil_de003', u'soil_de005']
    # areasymbolList = list of SSAs generated from SDA.  This will be empty when using the
    #                  the Create gSSURGO DB by Map tool

    try:

        # Creating the file geodatabase uses the ImportXMLWorkspaceDocument command which requires
        #
        # ArcInfo: Advanced license
        # ArcEditor: Standard license
        # ArcView: Basic license
        licenseLevel = arcpy.ProductInfo().upper()
        if licenseLevel == "BASIC":
            raise MyError, "ArcGIS License level must be Standard or Advanced to run this tool"

        env.overwriteOutput= True
        codePage = 'iso-8859-1'  # allow csv reader to handle non-ascii characters
        # According to Gary Spivak, SDM downloads are UTF-8 and NASIS downloads are iso-8859-1
        # cp1252 also seemed to work well
        #codePage = 'utf-16' this did not work
        #
        # http://stackoverflow.com/questions/6539881/python-converting-from-iso-8859-1-latin1-to-utf-8
        # Next need to try: string.decode('iso-8859-1').encode('utf8')

        dbVersion = 2  # This is the SSURGO version supported by this script and the gSSURGO schema (XML Workspace document)

        # Make sure that the env.scratchGDB is NOT Default.gdb. This can cause problems for
        # some unknown reason.
        #if (os.path.basename(env.scratchGDB).lower() == "default.gdb") or \
        #(os.path.basename(env.scratchWorkspace).lower() == "default.gdb") or \
        #(os.path.basename(env.scratchGDB).lower() == outputWS):

        # Import script to generate relationshipclasses and associated attribute indexes
        import Create_SSURGO_RelationshipClasses

        # get the information from the tileInfo
        if type(tileInfo) == tuple:
            if bClipped:
                # Set the aliasname when this is a clipped layer
                aliasName = ""
                description = tileInfo[1]

            else:
                # Try leaving the aliasname off of the regular layers.
                aliasName = tileInfo[0]
                description = tileInfo[1]

        else:
            stDict = StateNames()
            aliasName = tileInfo

            if aliasName in stDict:
                description = stDict[aliasName]

            else:
                description = tileInfo

        aliasName = ""

        #PrintMsg(" \nAlias and description: " + aliasName + "; " +  description, 1)

        # Get the XML Workspace Document appropriate for the specified AOI
        inputXML = GetXML(AOI)

        if inputXML == "":
            raise MyError, "Unable to set input XML Workspace Document"

        if len(surveyList) == 0:
            raise MyError, "At least one soil survey area input is required"

        #PrintMsg(" \nUsing " + inputXML + " to create GDB", 0)
        dList = dict()
        #areasymbolList = list()
        exportedList = list()
        extentList = list()
        mupolyList = list()
        mupointList = list()
        mulineList = list()
        sflineList = list()
        sfpointList = list()
        sapolyList = list()
        dbList = list()

        # Added this variable to represent the SSA prefix before the areasymbol i.e. soil_
        subFolderRoot = ""

        if len(areasymbolList) == 0:
            # The 'Create gSSURGO DB by Map' tool will skip this section because the SortSurveyAreas function
            # has already generated a spatial sort for the list of survey areas.
            #
            iSurveys = len(surveyList)
            PrintMsg(" \nCreating spatially sorted list for " + str(iSurveys) + " selected surveys...", 0)

            # SECTION A
            for subFolder in surveyList:

                # Perform spatial import
                # Req: inputFolder, subFolder
                # build the input shapefilenames for each SSURGO featureclass type using the
                # AREASYMBOL then confirm shapefile existence for each survey and append to final input list
                # used for the Append command. Use a separate list for each featureclass type so
                # that missing or empty shapefiles will not be included in the Merge. A separate
                # Append process is used for each featureclass type.

                # folder is named according to current WSS format i.e. WI001-----AD
                if len(subFolder) == 5:
                    areaSym = subFolder.lower()

                # WSS folder is named according to traditional SDM format i.e. 'soils_wa001'
                if subFolder.find("soil_") > -1 or subFolder.find("soils_") > -1:
                    areaSym = subFolder[-5:].lower()
                    subFolderRoot = "soil_"

                # folder is named in WSS 3.0 format i.e. 'wss_SSA_WI063_soildb_WI_2003_[2012-06-27]'
                elif subFolder.find("wss_SSA_") > -1:
                    areaSym = subFolder[subFolder.find("SSA_") + 4:subFolder.find("soildb")-1].lower()
                    subFolderRoot = "wss_SSA_"

                # folder is named outside of any WSS naming convention and AREASYMBOL
                # cannot be pulled out
                else:
                    pass

                #areaSym = subFolder[-5:].upper()#.encode('ascii')
                #areaSym = subFolder.upper()#.encode('ascii')
                #areaSym = subFolder[(subFolder.rfind("_") + 1):].lower()  # STATSGO mod

                env.workspace = os.path.join( inputFolder, os.path.join(subFolder, "spatial"))
                mupolyName = "soilmu_a_" + areaSym + ".shp"
                gsmupolyName = "gsmsoilmu_a_" + areaSym + ".shp"
                mulineName = "soilmu_l_" + areaSym + ".shp"
                mupointName = "soilmu_p_" + areaSym + ".shp"
                sflineName = "soilsf_l_" + areaSym + ".shp"
                sfpointName = "soilsf_p_" + areaSym + ".shp"
                sapolyName = "soilsa_a_" + areaSym + ".shp"
                arcpy.SetProgressorLabel("Getting extent for " + areaSym.upper() + " survey area")
                #PrintMsg(" \nProcessing "  + areaSym.upper() + " survey area", 1)

                if arcpy.Exists(mupolyName):
                    # Found soil polygon shapefile...
                    # Calculate the product of the centroid X and Y coordinates
                    desc = arcpy.Describe(mupolyName)
                    shpExtent = desc.extent

                    if shpExtent is None:
                        raise MyError, "Corrupt soil polygon shapefile for " + areaSym.upper() + "?"

                    XCntr = ( shpExtent.XMin + shpExtent.XMax) / 2.0
                    YCntr = ( shpExtent.YMin + shpExtent.YMax) / 2.0
                    #sortValue = (areaSym, round(XCntr, 1),round(YCntr, 1))  # center of survey area
                    sortValue = (areaSym, round(shpExtent.XMin, 1), round(shpExtent.YMax, 1)) # upper left corner of survey area
                    extentList.append(sortValue)
                    areasymbolList.append(areaSym.upper())

                elif arcpy.Exists(gsmupolyName):
                    # Found STATSGO soil polygon shapefile...
                    # Calculate the product of the centroid X and Y coordinates
                    desc = arcpy.Describe(gsmupolyName)
                    shpExtent = desc.extent

                    if shpExtent is None:
                        raise MyError, "Corrupt soil polygon shapefile for " + areaSym.upper() + "?"

                    XCntr = ( shpExtent.XMin + shpExtent.XMax) / 2.0
                    YCntr = ( shpExtent.YMin + shpExtent.YMax) / 2.0
                    #sortValue = (areaSym, round(XCntr, 1),round(YCntr, 1))  # center of survey area
                    sortValue = (areaSym, round(shpExtent.XMin, 1), round(shpExtent.YMax, 1)) # upper left corner of survey area
                    extentList.append(sortValue)
                    areasymbolList.append(areaSym.upper())

                else:
                    # Need to remove this if tabular-only surveys are allowed
                    raise MyError, "Error. Missing soil polygon shapefile: " + mupolyName + " in " + os.path.join( inputFolder, os.path.join( subFolder, "spatial"))

            # Make sure that the extentList is the same length as the surveyList. If it is
            # shorter, there may have been a duplicate sortKey which would result in a
            # survey being skipped in the merge
            env.workspace = inputFolder

            if len(extentList) < len(surveyList):
                raise MyError, "Problem with survey extent sort key"

            # Sort the centroid coordinate list so that the drawing order of the merged layer
            # is a little more efficient
            extentList.sort(key=itemgetter(1), reverse=False)
            extentList.sort(key=itemgetter(2), reverse=True)

            areasymbolList = list()
            cnt = 0
            #PrintMsg(" \nSpatially sorted list of areasymbols", 1)

            for sortValu in extentList:
                cnt += 1
                areasym = sortValu[0]
                areasymbolList.append(areasym)
                #PrintMsg(str(cnt) + "," + areasym.upper(), 1)

        else:
            # this section is primarily for the Create gSSURGO DB by map b/c areasymbollist
            # comes in populate so the above code doesn't get invoked.

            for subFolder in surveyList:

                # folder is named according to current WSS format i.e. WI001-----AD
                if len(subFolder) == 5:
                    areaSym = subFolder.lower()

                # WSS folder is named according to traditional SDM format i.e. 'soils_wa001'
                if subFolder.find("soil_") > -1 or subFolder.find("soils_") > -1:
                    areaSym = subFolder[-5:].lower()
                    subFolderRoot = "soil_"

                # folder is named in WSS 3.0 format i.e. 'wss_SSA_WI063_soildb_WI_2003_[2012-06-27]'
                elif subFolder.find("wss_SSA_") > -1:
                    areaSym = subFolder[subFolder.find("SSA_") + 4:subFolder.find("soildb")-1].lower()
                    subFolderRoot = "wss_SSA_"

                # folder is named outside of any WSS naming convention and AREASYMBOL
                # cannot be pulled out
                else:
                    pass

        # Save the total featurecount for all input shapefiles
        mupolyCnt = 0
        mulineCnt = 0
        mupointCnt = 0
        sflineCnt = 0
        sfpointCnt = 0
        sapolyCnt = 0

        # Create a series of lists that contain the found shapefiles to be merged
        PrintMsg(" \nCreating list of shapefiles to be imported for each of " + Number_Format(len(areasymbolList), 0, True) + " survey area...", 0)
        arcpy.SetProgressor("step", "Adding surveys to merge list", 1, len(areasymbolList))

        # Is there a reason this section couldn't be combined with SECTION A
        for areaSym in areasymbolList:
            #areaSym = sortValue[0]
            #subFolder = "soil_" + areaSym

            if len(subFolderRoot) > 0:
                subFolder = subFolderRoot + areaSym.lower()
            else:
                subFolder = areaSym

            shpPath = os.path.join(inputFolder, os.path.join( subFolder, "spatial"))

            badShps = list()

            # soil polygon shapefile
            mupolyName = "soilmu_a_" + areaSym + ".shp"
            gsmpolyName = "gsmsoilmu_a_" + areaSym + ".shp"
            muShp = os.path.join(shpPath, mupolyName)
            gsmuShp = os.path.join(shpPath, mupolyName)

            # SSURGO MUPOLYGON
            if arcpy.Exists(muShp):

                cnt = int(arcpy.GetCount_management(muShp).getOutput(0))

                if cnt > 0:
                    if not muShp in mupolyList:
                        mupolyCnt += cnt
                        mupolyList.append(muShp)
                        #PrintMsg("\tAdding '" + areaSym.upper() + "' survey to merge list with " + str(cnt) + " polygons", 0)
                        arcpy.SetProgressorLabel("Adding " + areaSym.upper() + " survey to merge list")

                else:
                    badShps.append(shpFile)
                    #raise MyError, "No features found in " + shpFile

            # STATSGO MUPOLYGON
            elif arcpy.Exists(gsmuShp):

                cnt = int(arcpy.GetCount_management(gsmuShp).getOutput(0))

                if cnt > 0:
                    if not gsmuShp in mupolyList:
                        mupolyCnt += cnt
                        mupolyList.append(gsmuShp)
                        #PrintMsg("\tAdding '" + areaSym.upper() + "' survey to merge list", 0)
                        arcpy.SetProgressorLabel("Adding " + areaSym.upper() + " survey to merge list")

                else:
                    badShps.append(gsmuShp)
                    #raise MyError, "No features found in " + gsmuShp

            else:
                raise MyError, "Shapefile " + muShp + " not found"

            # input soil polyline shapefile
            mulineName = "soilmu_l_" + areaSym + ".shp"
            shpFile = os.path.join(shpPath, mulineName)

            if arcpy.Exists(shpFile):
                cnt = int(arcpy.GetCount_management(shpFile).getOutput(0))

                if cnt > 0:
                    if not shpFile in mulineList:
                        mulineCnt += cnt
                        mulineList.append(shpFile)

            # input soil point shapefile
            mupointName = "soilmu_p_" + areaSym + ".shp"
            shpFile = os.path.join(shpPath, mupointName)

            if arcpy.Exists(shpFile):
                cnt = int(arcpy.GetCount_management(shpFile).getOutput(0))

                if cnt > 0:
                    mupointCnt += cnt
                    mupointList.append(shpFile)

            # input specialfeature polyline shapefile name
            sflineName = "soilsf_l_" + areaSym + ".shp"
            shpFile = os.path.join(shpPath, sflineName)

            if arcpy.Exists(shpFile):
                cnt = int(arcpy.GetCount_management(shpFile).getOutput(0))

                if cnt > 0:
                    if not shpFile in sflineList:
                        sflineCnt += cnt
                        sflineList.append(shpFile)

            # input special feature point shapefile
            sfpointName = "soilsf_p_" + areaSym + ".shp"
            shpFile = os.path.join(shpPath, sfpointName)

            if arcpy.Exists(shpFile):
                cnt = int(arcpy.GetCount_management(shpFile).getOutput(0))
                #PrintMsg(" \nCounted " + str(cnt) + " features in " + shpFile, 1)

                if cnt > 0:
                    if not shpFile in sfpointList:
                        sfpointCnt += cnt
                        sfpointList.append(shpFile)

            # input soil survey boundary shapefile name
            sapolyName = "soilsa_a_" + areaSym + ".shp"
            shpFile = os.path.join(shpPath, sapolyName)

            if arcpy.Exists(shpFile):
                cnt = int(arcpy.GetCount_management(shpFile).getOutput(0))

                if cnt > 0:
                    if not shpFile in sapolyList:
                        cnt = int(arcpy.GetCount_management(shpFile).getOutput(0))
                        sapolyCnt += cnt
                        sapolyList.append(shpFile)

            # input soil survey Template database
            if useTextFiles == True:
                # use database path, even if it doesn't exist. It will be used
                # to actually define the location of the tabular folder and textfiles
                # probably need to fix this later
                dbPath = os.path.join( inputFolder, os.path.join( subFolder, "tabular"))
                dbName = "soil_d_" + areaSym + ".mdb"
                dbFile = os.path.join(dbPath, dbName)

                if not dbFile in dbList:
                    dbList.append(dbFile)

            else:
                dbPath = os.path.join( inputFolder, os.path.join( subFolder, "tabular"))
                dbName = "soil_d_" + areaSym + ".mdb"
                dbFile = os.path.join(dbPath, dbName)

                if arcpy.Exists(dbFile) and not dbFile in dbList:
                    dbList.append(dbFile)

                else:
                    PrintMsg("Missing Template database (" + dbName + ")", 2)
                    return False

            arcpy.SetProgressorPosition()

        if len(badShps) > 0:
            raise MyError, "Found " + Number_Format(len(badShps), 0, True) + " soil polygon shapefiles with no data: " + "\n".join(badShps)

        time.sleep(1)
        arcpy.ResetProgressor()

        if len(mupolyList) > 0:
            # Create file geodatabase for output data
            # Remove any dashes in the geodatabase name. They will cause the
            # raster conversion to fail for some reason.
            gdbName = os.path.basename(outputWS)
            outFolder = os.path.dirname(outputWS)
            gdbName = gdbName.replace("-", "_")
            outputWS = os.path.join(outFolder, gdbName)
            featCnt = (mupolyCnt, mulineCnt, mupointCnt, sflineCnt, sfpointCnt, sapolyCnt)  # 0 mupoly, 1 muline, 2 mupoint, 3 sfline, 4 sfpoint, 5 sapoly

            bGeodatabase = CreateSSURGO_DB(outputWS, inputXML, areasymbolList, aliasName)

            if bGeodatabase:
                # Successfully created a new geodatabase
                # Merge all existing shapefiles to file geodatabase featureclasses
                #
                env.workspace = outputWS  # attempted metadata-workspace conflict fix

                bSpatial = AppendFeatures(outputWS, AOI, mupolyList, mulineList, mupointList, sflineList, sfpointList, sapolyList, featCnt)

                # Append tabular data to the file geodatabase
                #
                if bSpatial == True:
                    if not arcpy.Exists(outputWS):
                        raise MyError, "Could not find " + outputWS + " to append tables to"

                    if useTextFiles:
                        bMD = ImportMDTabular(outputWS, dbPath, codePage)  # new, import md tables from text files of last survey area

                        if bMD == False:
                            raise MyError, ""

                        # import attribute data from text files in tabular folder
                        bTabular = ImportTabular(outputWS, dbList, dbVersion, codePage)

                    else:
                        bMD = ImportMDTables(outputWS, dbList)

                        if bMD == False:
                            raise MyError, ""

                        # import attribute data from Template database tables
                        bTabular = ImportTables(outputWS, dbList, dbVersion)

                    if bTabular == True:
                        # Successfully imported all tabular data (textfiles or Access database tables)
                        PrintMsg(" \nAll spatial and tabular data imported", 0)

                    else:
                        PrintMsg("Failed to export all data to gSSURGO. Tabular export error.", 2)
                        return False

                else:
                    PrintMsg("Failed to export all data to gSSURGO. Spatial export error", 2)
                    return False

            else:
                return False

            # In October 2018 it was reported that two of the DHS interps were missing from the sdv tables
            # This is a patch to replace the 4 missing records
            #bFixed = IdentifyNewInterps(outputWS)

            # Create table relationships and indexes
            bRL = CreateTableRelationships(outputWS)

            # Query the output SACATALOG table to get list of surveys that were exported to the gSSURGO
            #
            saTbl = os.path.join(outputWS, "sacatalog")
            expList = list()
            queryList = list()

            with arcpy.da.SearchCursor(saTbl, ["AREASYMBOL", "SAVEREST"]) as srcCursor:
                for rec in srcCursor:
                    expList.append(rec[0] + " (" + str(rec[1]).split()[0] + ")")
                    queryList.append("'" + rec[0] + "'")

            surveyInfo = ", ".join(expList)
            queryInfo = ", ".join(queryList)

            # Update metadata for the geodatabase and all featureclasses
            PrintMsg(" \nUpdating metadata...", 0)
            arcpy.SetProgressorLabel("Updating metadata...")
            mdList = [outputWS, os.path.join(outputWS, "FEATLINE"), os.path.join(outputWS, "FEATPOINT"), \
            os.path.join(outputWS, "MUPOINT"), os.path.join(outputWS, "MULINE"), os.path.join(outputWS, "MUPOLYGON"), \
            os.path.join(outputWS, "SAPOLYGON")]
            #remove_gp_history_xslt = os.path.join(os.path.dirname(sys.argv[0]), "remove geoprocessing history.xslt")

##            if not arcpy.Exists(remove_gp_history_xslt):
##                raise MyError, "Missing required file: " + remove_gp_history_xslt

            for target in mdList:
                bMetadata = UpdateMetadata(outputWS, target, surveyInfo, description)

            del target
            del mdList

            PrintMsg(" \nCompacting new database", 0)
            arcpy.SetProgressorLabel("Compacting new database...")
            arcpy.Compact_management(outputWS)

            wsDesc = arcpy.Describe(outputWS)
            arcpy.RefreshCatalog(outputWS)

            # Check scratchfolder for xxImport*.log files
            # For some reason they are being put in the folder above env.scratchFolder (or is it one above scratchworkspace?)

            env.workspace = os.path.dirname(env.scratchFolder)
            #PrintMsg(" \nCleaning log files from " + env.workspace, 1)

            logFiles = arcpy.ListFiles("xxImport*.log")

            if len(logFiles) > 0:
                #PrintMsg(" \nFound " + str(len(logFiles)) + " log files in " + env.workspace, 1)
                for logFile in logFiles:
                    #PrintMsg("\t\tDeleting " + logFile, 1)
                    arcpy.Delete_management(logFile)


            PrintMsg(" \nSuccessfully created a geodatabase containing the following surveys: " + queryInfo, 0)
            arcpy.SetProgressorLabel("Successfully created new gSSURGO database...")

        PrintMsg(" \nOutput file geodatabase:  " + outputWS + "  \n ", 0)

        del  outputWS, gdbName, outFolder

        return True

    except MyError, e:
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return True

## ===================================================================================
def SortSurveyAreaLayer(ssaLayer, surveyList):
    # For the 'Create gSSURGO DB by Map' sort the polygons by extent and use that to regenerate the surveyList
    #
    try:
        # first reformat the surveyList (soil_areasymbol.lower())
        newSurveyList = list()

        # update this - AD
        areasymList = [s[-5:].upper() for s in surveyList]
        sortedSSA = os.path.join(env.scratchGDB, "sortedSSA")
        desc = arcpy.Describe(ssaLayer)
        shapeField = desc.featureclass.shapeFieldName

        if arcpy.Exists(sortedSSA):
            arcpy.Delete_management(sortedSSA)

        arcpy.Sort_management(ssaLayer, sortedSSA, shapeField, "UR")
        #PrintMsg(" \nareasymList: " + str(areasymList), 1)

        if arcpy.Exists(sortedSSA):
            with arcpy.da.SearchCursor(sortedSSA, "areasymbol", ) as cur:
                for rec in cur:
                    areaSym = rec[0].encode('ascii')
                    #PrintMsg(areaSym, 1)

                    if areaSym in areasymList and not areaSym in newSurveyList:
                        newSurveyList.append(areaSym)

        else:
            raise MyError, "Failed to produce spatial sort on survey areas"

        #PrintMsg(" \nnewSurveyList: " + str(newSurveyList), 1)

        return newSurveyList


    except MyError, e:
        PrintMsg(str(e), 2)
        return []

    except:
        errorMsg()
        return []

## ===================================================================================
def FindField(theInput, chkField, bVerbose = False):
    # Check table or featureclass to see if specified field exists
    # If fully qualified name is found, return that
    # Set workspace before calling FindField
    try:
        if arcpy.Exists(theInput):
            theDesc = arcpy.Describe(theInput)
            theFields = theDesc.Fields
            #theField = theFields.next()
            # Get the number of tokens in the fieldnames
            #theNameList = arcpy.ParseFieldName(theField.Name)
            #theCnt = len(theNameList.split(",")) - 1

            for theField in theFields:
                theNameList = arcpy.ParseFieldName(theField.Name)
                theCnt = len(theNameList.split(",")) - 1
                theFieldname = theNameList.split(",")[theCnt].strip()

                if theFieldname.upper() == chkField.upper():
                    return theField.Name

                #theField = theFields.next()

            if bVerbose:
                PrintMsg("Failed to find column " + chkField + " in " + theInput, 2)

            return ""

        else:
            PrintMsg("\tInput layer not found", 0)
            return ""

    except:
        errorMsg()
        return ""

## ===============================================================================================================
def CreateTableRelationships(wksp):
    # Create relationship classes between standalone attribute tables.
    # Relate parameters are pulled from the mdstatrhipdet and mdstatrshipmas tables,
    # thus it is required that the tables must have been copied from the template database.

    try:

        PrintMsg(" \nCreating table relationships and indexes on key fields...", 0)
        env.workspace = wksp

        if arcpy.Exists(os.path.join(wksp, "mdstatrshipdet")) and arcpy.Exists(os.path.join(wksp, "mdstatrshipmas")):

            # Create new Table View to contain results of join between relationship metadata tables

            tbl1 = os.path.join(wksp, "mdstatrshipmas")
            tbl2 = os.path.join("mdstatrshipdet")
            tblList = [tbl1, tbl2]
            queryTableName = "TblRelationships"

            sql = "mdstatrshipdet.ltabphyname = mdstatrshipmas.ltabphyname AND mdstatrshipdet.rtabphyname = mdstatrshipmas.rtabphyname AND mdstatrshipdet.relationshipname = mdstatrshipmas.relationshipname"

            fldList = [["mdstatrshipmas.ltabphyname","LTABPHYNAME"],["mdstatrshipmas.rtabphyname", "RTABPHYNAME"],["mdstatrshipdet.relationshipname", "RELATIONSHIPNAME"], ["mdstatrshipdet.ltabcolphyname", "LTABCOLPHYNAME"],["mdstatrshipdet.rtabcolphyname",  "RTABCOLPHYNAME"]]

            arcpy.MakeQueryTable_management (tblList, queryTableName, "ADD_VIRTUAL_KEY_FIELD", "", fldList, sql)

            if not arcpy.Exists(queryTableName):
                raise MyError, "Failed to create metadata table required for creation of relationshipclasses"

            tblCnt = int(arcpy.GetCount_management(queryTableName).getOutput(0)) + 7
            #PrintMsg(" \nQuery table has " + str(tblCnt) + " records", 1)
            arcpy.SetProgressor("step", "Creating table relationships...", 1, tblCnt, 1)
            #arcpy.CopyRows_management(queryTableName, os.path.join(env.scratchGDB, "MdTable"))

            # Fields in RelshpInfo table view
            # OBJECTID, LTABPHYNAME, RTABPHYNAME, RELATIONSHIPNAME, LTABCOLPHYNAME, RTABCOLPHYNAME
            # Open table view and step through each record to retrieve relationshipclass parameters
            with arcpy.da.SearchCursor(queryTableName, ["mdstatrshipmas_ltabphyname", "mdstatrshipmas_rtabphyname", "mdstatrshipdet_ltabcolphyname", "mdstatrshipdet_rtabcolphyname"]) as theCursor:

                for rec in theCursor:
                    # Get relationshipclass parameters from current table row
                    # Syntax for CreateRelationshipClass_management (origin_table, destination_table,
                    # out_relationship_class, relationship_type, forward_label, backward_label,
                    # message_direction, cardinality, attributed, origin_primary_key,
                    # origin_foreign_key, destination_primary_key, destination_foreign_key)
                    #
                    destinationTable, originTable, originFKey, originPKey = rec

                    originTablePath = os.path.join(wksp, originTable)
                    destinationTablePath = os.path.join(wksp, destinationTable)

                    # Use table aliases for relationship labels
                    relName = "z" + originTable.title() + "_" + destinationTable.title()

                    if arcpy.Exists(relName):
                        arcpy.Delete_management(relName)

                    # create Forward Label i.e. "> Horizon AASHTO Table"
                    fwdLabel = "< " + destinationTable.title() + " Table"

                    # create Backward Label i.e. "< Horizon Table"
                    backLabel = ">  " + originTable.title() + " Table"

                    if arcpy.Exists(originTablePath) and arcpy.Exists(destinationTablePath):
                        arcpy.SetProgressorLabel("Creating table relationship between " + originTable + " and " + destinationTable)
                        arcpy.CreateRelationshipClass_management(originTablePath, destinationTablePath, relName, "SIMPLE", fwdLabel, backLabel, "NONE", "ONE_TO_MANY", "NONE", originPKey, originFKey, "","")

                    arcpy.SetProgressorPosition()

        else:
            raise MyError, "Missing one or more of the metadata tables"


        # Establish Relationship between tables and Spatial layers
        #
        arcpy.SetProgressorLabel("Creating relationships for featureclasses...")

        # Relationship between MUPOLYGON --> Mapunit Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "mapunit"), os.path.join(wksp, "MUPOLYGON"), os.path.join(wksp, "zSpatial_MUPOLYGON_Mapunit"), "SIMPLE", "< MUPOLYGON_Spatial", "> Mapunit Table", "NONE","ONE_TO_MANY", "NONE","MUKEY","mukey", "","")
        arcpy.SetProgressorPosition()

        # Relationship between MUPOLYGON --> Mapunit Aggregate Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "muaggatt"), os.path.join(wksp, "MUPOLYGON"), os.path.join(wksp, "zSpatial_MUPOLYGON_Muaggatt"), "SIMPLE", "< MUPOLYGON_Spatial", "> Mapunit Aggregate Table", "NONE","ONE_TO_MANY", "NONE","MUKEY","mukey", "","")
        arcpy.SetProgressorPosition()

        # Relationship between SAPOLYGON --> Legend Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "legend"), os.path.join(wksp, "SAPOLYGON"), os.path.join(wksp, "zSpatial_SAPOLYGON_Legend"), "SIMPLE", "< SAPOLYGON_Spatial", "> Legend Table", "NONE","ONE_TO_MANY", "NONE","LKEY","lkey", "","")
        arcpy.SetProgressorPosition()

        # Relationship between MULINE --> Mapunit Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "mapunit"), os.path.join(wksp, "MULINE"), os.path.join(wksp, "zSpatial_MULINE_Mapunit"), "SIMPLE", "< MULINE_Spatial", "> Mapunit Table", "NONE","ONE_TO_MANY", "NONE","MUKEY","mukey", "","")
        arcpy.SetProgressorPosition()

        # Relationship between MUPOINT --> Mapunit Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "mapunit"), os.path.join(wksp, "MUPOINT"), os.path.join(wksp, "zSpatial_MUPOINT_Mapunit"), "SIMPLE", "< MUPOINT_Spatial", "> Mapunit Table", "NONE","ONE_TO_MANY", "NONE","MUKEY","mukey", "","")
        arcpy.SetProgressorPosition()

        # Relationship between FEATLINE --> Featdesc Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "featdesc"), os.path.join(wksp, "FEATLINE"), os.path.join(wksp, "zSpatial_FEATLINE_Featdesc"), "SIMPLE", "< SPECLINE_Spatial", "> Featdesc Table", "NONE","ONE_TO_MANY", "NONE","FEATKEY","featkey", "","")
        arcpy.SetProgressorPosition()

        # Relationship between FEATPOINT --> Featdesc Table
        arcpy.CreateRelationshipClass_management(os.path.join(wksp, "featdesc"), os.path.join(wksp, "FEATPOINT"), os.path.join(wksp, "zSpatial_FEATPOINT_Featdesc"), "SIMPLE", "< SPECPOINT_Spatial", "> Featdesc Table", "NONE","ONE_TO_MANY", "NONE","FEATKEY","featkey", "","")
        arcpy.SetProgressorPosition()

        PrintMsg("\nSuccessfully created featureclass and table relationships", 0)
        arcpy.ResetProgressor()

        return True


    except:
        errorMsg()
        return False

## ===================================================================================
def GetFCType(fc):
    # Determine featureclass typefeaturetype and table fields
    # Rename featureclasses from old shapefile-based name to new, shorter name
    # Returns new featureclass name using DSS convention for geodatabase
    #
    # The check for table fields is the absolute minimum

    featureType = ""

    # Look for minimum list of required fields
    #

    if FindField(fc, "MUSYM"):
        hasMusym = True

    else:
        hasMusym = False

    if FindField(fc, "LKEY"):
        hasLkey = True

    else:
        hasLkey = False

    if FindField(fc, "FEATSYM"):
        hasFeatsym = True

    else:
        hasFeatsym = False

    try:
        fcName = os.path.basename(fc)
        theDescription = arcpy.Describe(fc)
        featType = theDescription.ShapeType

        # Mapunit Features
        if hasMusym:
            if featType == "Polygon" and fcName.upper() != "MUPOINT":
                dataType = "Mapunit Polygon"

            elif featType == "Polyline":
                dataType = "Mapunit Line"

            elif featType == "Point" or featType == "Multipoint" or fcName.upper() == "MUPOINT":
                dataType = "Mapunit Point"

            else:
                PrintMsg(fcName + " is an unidentified " + featType + " featureclass with an MUSYM field (GetFCName)", 2)
                featureType = ""



        # Survey Area Boundary
        elif hasLkey:
            if featType == "Polygon":
                dataType = "Survey Boundary"

            else:
                PrintMsg(fcName + " is an unidentified " + featType + " featureclass with an LKEY field (GetFCName)", 2)
                dataType = ""

        # Special Features
        elif hasFeatsym:
            # Special Feature Line
            if featType == "Polyline":
                dataType = "Special Feature Line"

            # Special Feature Point
            elif featType == "Point" or featType == "Multipoint":
                dataType = "Special Feature Point"

            else:
                PrintMsg(fcName + " is an unidentified " + featType + " featureclass with an FEATSYM field (GetFCName)", 2)
                dataType = ""

        PrintMst(" \n" + fc + " data type is " + dataType, 1)
        return dataType

    except:
        errorMsg()
        return ""

## ===================================================================================

# Import system modules
import arcpy, sys, string, os, traceback, locale, time, datetime, csv
from operator import itemgetter, attrgetter
import xml.etree.cElementTree as ET
from arcpy import env

try:
    if __name__ == "__main__":
        inputFolder = arcpy.GetParameterAsText(0)     # location of SSURGO datasets containing spatial folders
        # skip parameter 1.                           # Survey boundary layer (only used within Validation code)
        # The following line references parameter 1 in the other script and is the only change
        ssaLayer = arcpy.GetParameterAsText(1)        # Test to see if I can sort the ssaLayer when using the 'Create gSSURGO DB by Map' tool
        surveyList = arcpy.GetParameter(2)            # list of SSURGO dataset folder names to be proccessed (soil_*)
        outputWS = arcpy.GetParameterAsText(3)        # Name of output geodatabase
        AOI = arcpy.GetParameterAsText(4)             # Geographic Region used to set output coordinate system
        aliasName = arcpy.GetParameterAsText(5)       # String to be appended to featureclass aliases
        useTextFiles = arcpy.GetParameter(6)

        #dbVersion = 2  # This is the SSURGO version supported by this script and the gSSURGO schema (XML Workspace document)

        # Check to see if we got an ssaLayer
        #PrintMsg(" \nInput ssaLayer: " + ssaLayer, 1)

        if arcpy.Exists(ssaLayer):
            # Sort_management (in_dataset, out_dataset, sort_field, {spatial_sort_method})
            areasymbolList = SortSurveyAreaLayer(ssaLayer, surveyList)

        else:
            areasymbolList = list()


        bGood = gSSURGO(inputFolder, surveyList, outputWS, AOI, aliasName, useTextFiles, False, areasymbolList)

except MyError, e:
    PrintMsg(str(e), 2)

except:
    errorMsg()
