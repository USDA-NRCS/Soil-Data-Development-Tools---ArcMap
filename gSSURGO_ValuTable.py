# gSSURGO_ValuTable.py
#
# Steve Peaslee, National Soil Survey Center
# 2014-09-27

# Adapted from HorizonData_Mapping
# Calculates root zone depth, root zone available water supply and a set of
# available water supply values at various defined depth ranges.
#
# The root zone available water supply is calculated down to the root zone for
# each component and then a weighted average is calculated for the map unit.
#
# The rest of the AWS columns are calculated for all components at a variety of depths.
# Output is to a geodatabase table (Valu1)
#
# To do list for FY2016....
# In order for this script to meet the 2015 standard for the Valu1 table it needs to:
#   skip components where compkind is null
#   stop horizon calculations for all data where there is a discrepancy in horizon depths
#   null map unit AWS, SOC and PWSL values where sum of all components > 100
#   null Rootzone Depth, Rootzone AWS and NCCPI* where sum of major components > 100
#   perform independent validation of SOC results
#   compare metadata dates to make sure they are properly coded and inserted
#   look at array processing for calculations based upon depth ranges
#
# changed the OM to carbon conversion from * 0.58 to / 1.724 after running FY2017 value table

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
        #locale.setlocale(locale.LC_ALL, "")
        locale.getlocale()

        if bCommas:
            theNumber = locale.format("%.*f", (places, num), True)

        else:
            theNumber = locale.format("%.*f", (places, num), False)
        return theNumber

    except:
        PrintMsg("Unhandled exception in Number_Format function (" + str(num) + ")", 2)
        return False

## ===================================================================================
def GetLastDate(inputDB):
    # Get the most recent date 'YYYYMMDD' from SACATALOG.SAVEREST and use it to populate metadata
    #
    try:
        tbl = os.path.join(inputDB, "SACATALOG")
        today = ""
        sqlClause = [None, "ORDER BY SAVEREST DESC"]

        with arcpy.da.SearchCursor(tbl, ['SAVEREST'], sql_clause=sqlClause) as cur:
            for rec in cur:
                #lastDate = rec[0].split(" ")[0].replace("-", "")
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
def CreateQueryTables(inputDB, outputDB, maxD):
    #
    try:
        env.workspace = inputDB
        queryMU = "MU"
        queryCO = "CO"
        queryHZ = "HZ"
        queryCR = "CR"
        queryCT = "CT"
        queryTemp = "Tmp"  # empty table uses as template

        # Create an empty table using the original queryHZ as a template

        # MAPUNIT TABLE
        #
        PrintMsg(" \n\tReading MAPUNIT table...", 0)
        whereClause = ""
        fldMu = [["mukey", "mukey"], ["musym", "musym"], ["muname", "muname"]]
        fldMu2 = list()
        dMu = dict()
        sqlClause = (None, "ORDER BY mukey")

        for fld in fldMu:
            fldMu2.append(fld[0])

        muList = list()

        muTbl = os.path.join(inputDB, "mapunit")

        with arcpy.da.SearchCursor(muTbl, fldMu2, sql_clause=sqlClause) as mcur:
            for mrec in mcur:
                rec = list(mrec)
                mukey = rec[0]
                #mukey = int(rec[0])
                rec.pop(0)
                dMu[mukey] = rec
                muList.append(mukey)

        muList.sort()

        del muTbl

        # COMPONENT TABLE
        #
        PrintMsg(" \n\tReading COMPONENT table...", 0)
        fldCo = [["mukey", "mukey"], ["cokey", "cokey"], ["comppct_r", "comppct_r"], ["majcompflag", "majcompflag"], \
        ["compname", "compname"], ["compkind", "compkind"], ["taxorder", "taxorder"], ["taxsubgrp", "taxsubgrp"], \
        ["localphase", "localphase"], ["otherph", "otherph"], ["hydricrating", "hydricrating"], ["drainagecl", "drainagecl"]]
        fldCo2 = list()
        dCo = dict()
        whereClause = "comppct_r is not NULL"
        sqlClause = (None, "ORDER BY cokey, comppct_r DESC")
        coTbl = os.path.join(inputDB, "component")

        for fld in fldCo:
            fldCo2.append(fld[0])

        with arcpy.da.SearchCursor(coTbl, fldCo2, where_clause=whereClause, sql_clause=sqlClause) as ccur:
            for crec in ccur:
                rec = list(crec)
                mukey = rec.pop(0)  # get rid of mukey from component record

                try:
                    # Add next component record to list
                    dCo[mukey].append(rec)

                except:
                    # initialize list of records
                    dCo[mukey] = [rec]

        del coTbl

        # HORIZON TABLE
        #
        PrintMsg(" \n\tReading HORIZON table...", 0)
        fldHz = [["cokey", "cokey"], ["chkey", "chkey"], ["hzname", "hzname"], ["desgnmaster", "desgnmaster"], \
        ["hzdept_r", "hzdept_r"], ["hzdepb_r", "hzdepb_r"], ["sandtotal_r", "sandtotal_r"], \
        ["silttotal_r", "silttotal_r"], ["claytotal_r", "claytotal_r"], ["om_r", "om_r"], \
        ["dbthirdbar_r", "dbthirdbar_r"], ["ec_r", "ec_r"], ["ph1to1h2o_r", "ph1to1h2o_r"], \
        ["awc_r", "awc_r"]]
        fldHz2 = list()
        dHz = dict()
        whereClause = "hzdept_r is not NULL and hzdepb_r is not NULL"
        sqlClause = (None, "ORDER BY chkey, hzdept_r ASC")

        for fld in fldHz:
            fldHz2.append(fld[0])

        hzTbl = os.path.join(inputDB, "chorizon")

        with arcpy.da.SearchCursor(hzTbl, fldHz2, where_clause=whereClause, sql_clause=sqlClause) as hcur:
            for hrec in hcur:
                rec = list(hrec)
                cokey = rec.pop(0)

                try:
                    # Add next horizon record to list
                    dHz[cokey].append(rec)

                except:
                    # initialize list of horizon records
                    dHz[cokey] = [rec]

        del hzTbl

        # HORIZON TEXTURE
        #
        #PrintMsg(" \n\tMaking query table (CT) for texture information", 0)
        inputTbls = list()
        tbls = ["chtexturegrp", "chtexture"]
        for tbl in tbls:
            inputTbls.append(os.path.join(inputDB, tbl))

        txList1 = [["chtexturegrp.chkey", "chkey"], ["chtexturegrp.texture", "texture"], ["chtexture.lieutex", "lieutex"]]
        whereClause = "chtexturegrp.chtgkey = chtexture.chtgkey and chtexturegrp.rvindicator = 'Yes'"
        arcpy.MakeQueryTable_management(inputTbls, queryCT, "USE_KEY_FIELDS", "#", txList1, whereClause)

        # Try to overcome memory error by copying this query table to disk
        textureTbl = os.path.join(env.scratchGDB, "HzTexture")
        arcpy.TableToTable_conversion(queryCT, os.path.dirname(textureTbl), os.path.basename(textureTbl))
        arcpy.Delete_management(queryCT)
        del queryCT

        #raise MyError, "EARLY OUT"

        # Read texture query into dictionary
        #txList2 = ["chtexturegrp.chkey", "chtexturegrp.texture", "chtexture.lieutex"]
        txList2 = ["chkey", "texture", "lieutex"]
        dTexture = dict()
        ctCnt = int(arcpy.GetCount_management(textureTbl).getOutput(0))

        arcpy.SetProgressor ("step", "Getting horizon texture information for QueryTable_HZ...", 0, ctCnt, 1)

        # Have been running out of memory here if other applications are running. 5.66GB
        lieuList = ['Slightly decomposed plant material', 'Moderately decomposed plant material', \
        'Highly decomposed plant material', 'Undecomposed plant material', 'Muck', 'Mucky peat', \
        'Peat', 'Coprogenous earth']
        txList = ["CE", "COP-MAT", "HPM", "MPM", "MPT", "MUCK", "PDOM", "PEAT", "SPM", "UDOM"]
        #cnt = 0

        with arcpy.da.SearchCursor(textureTbl, txList2) as cur:
            for rec in cur:
                if (rec[1] in txList or rec[2] in lieuList):
                    #cnt +=1
                    #arcpy.SetProgressorLabel(str(cnt))
                    dTexture[rec[0]] = [rec[1], rec[2]]
                arcpy.SetProgressorPosition()

        arcpy.Delete_management(textureTbl)


        del textureTbl

        # COMPONENT RESTRICTIONS which will be saved to a gdb table
        #
        if arcpy.Exists(os.path.join(outputDB, "QueryTable_CR")):
            arcpy.Delete_management(os.path.join(outputDB, "QueryTable_CR"))

        crTbl = os.path.join(inputDB, "corestrictions")
        #PrintMsg(" \n\tReading component restriction data...", 0)
        fldCr = [["cokey", "cokey"], \
        ["reskind", "reskind"],\
        ["reshard", "reshard"],\
        ["resdept_r", "resdept_r"]]
        whereClause = "OBJECTID = 1"
        arcpy.MakeQueryTable_management(crTbl, queryCR, "USE_KEY_FIELDS", "#", fldCr, whereClause)
        arcpy.CreateTable_management(outputDB, "QueryTable_CR", queryCR)
        arcpy.Delete_management(queryCR)
        del queryCR

        fldCr2 = list()
        dCr = dict()
        sqlClause = (None, "ORDER BY cokey, resdept_r ASC")

        for fld in fldCr:
            fldCr2.append(fld[0])

        whereClause = "resdept_r is not NULL and resdept_r < " + str(maxD)
        outputCR = os.path.join(outputDB, "QueryTable_CR")
        crList = list() # list of components with a restriction
        crCnt = int(arcpy.GetCount_management(crTbl).getOutput(0))
        arcpy.SetProgressor ("step", "Saving component restriction information...", 0, crCnt, 1)

        with arcpy.da.SearchCursor(crTbl, fldCr2, where_clause=whereClause, sql_clause=sqlClause) as crcur:

            for crrec in crcur:
                rec = list(crrec)
                cokey = rec[0]
                arcpy.SetProgressorPosition()

                if not cokey in crList:
                    # Only save the highest level restriction above 150cm
                    crList.append(cokey)
                    dCr[cokey] = rec

        #PrintMsg(" \n\tCreating QueryTable_HZ in " + outputDB, 0)
        fldCo.pop(0)
        fldCo2.pop(0)
        fldHz.pop(0)
        fldHz2.pop(0)

        # Create list of fields for query table
        fldAll = list()
        # Create list of fields for output cursor
        fldAll2 = list()

        for fld in fldMu:
            fldAll.append(["mapunit." + fld[0], fld[1]])
            fldAll2.append(fld[1])

        for fld in fldCo:
            fldAll.append(["component." + fld[0], fld[1]])
            fldAll2.append(fld[1])

        for fld in fldHz:
            fldAll.append(["chorizon." + fld[0], fld[1]])
            fldAll2.append(fld[1])

        # Texture fields:
        fldAll2.append("texture")
        fldAll2.append("lieutex")

        # Select component-horizon data for ALL components that have horizon data. Lack of horizon data
        # will cause some components to be missing from the PWSL.
        #
        # Later on in the actual calculations for RZAWS, only the major-earthy components will be used. But
        # all components are in this table!

        whereClause = "mapunit.mukey = component.mukey and \
        component.cokey = chorizon.cokey and mapunit.objectid = 1"

        outputTable = os.path.join(outputDB, "QueryTable_HZ")
        PrintMsg(" \nCreating table " + outputTable, 0)

        if arcpy.Exists(os.path.join(outputDB, "QueryTable_HZ")):
            arcpy.Delete_management(os.path.join(outputDB, "QueryTable_HZ"))

        arcpy.MakeQueryTable_management(['mapunit', 'component', 'chorizon'], queryTemp, "USE_KEY_FIELDS", "#", fldAll, whereClause)
        arcpy.CreateTable_management(outputDB, "QueryTable_HZ", queryTemp)
        arcpy.AddField_management(outputTable, "texture", "TEXT", "", "", "30", "texture")
        arcpy.AddField_management(outputTable, "lieutex", "TEXT", "", "", "254", "lieutex")
        arcpy.Delete_management(queryTemp)
        del queryTemp

        # Process dictionaries and use themtextureTbl to write out the new QueryTable_HZ table
        #
        # Open output table
        #if arcpy.Exist(theMuTable):
        #    arcpy.Delete_management(theMuTable)

        outFld2 = arcpy.Describe(outputTable).fields
        outFlds = list()
        for fld in outFld2:
            outFlds.append(fld.name)

        outFlds.pop(0)

        # Create empty lists to replace missing data
        missingCo = ["", None, None, None, None, None, None, None, None, None, None]
        missingHz = ["", None, None, None, None, None, None, None, None, None, None, None, None]
        missingTx = [None, None]

        # Save information on mapunits or components with bad or missing data
        #badMu = list()   # list of mapunits with no components
        muNoCo = list()
        dNoCo = dict()
        coNoHz = list()  # list of components with no horizons
        dNoHz = dict() # component data for those components in coNoHz
        arcpy.SetProgressor ("step", "Writing data to " + outputTable + "...", 0, len(muList), 1)

        with arcpy.da.InsertCursor(outputTable, fldAll2) as ocur:

            for mukey in muList:
                mrec = dMu[mukey]
                arcpy.SetProgressorPosition()

                try:
                    coVals = dCo[mukey]  # got component records for this mapunit

                    # Sort lists by comppct_r
                    coList = sorted(coVals, key = lambda x: int(x[1]))

                    for corec in coList:
                        cokey = corec[0]

                        try:
                            hzVals = dHz[cokey]  # horizon records for this component
                            # Sort record by hzdept_r
                            hzList = sorted(hzVals, key = lambda x: int(x[3]))

                            for hzrec in hzList:
                                chkey = hzrec[0]

                                try:
                                    # Get horizon texture
                                    txrec = dTexture[chkey]

                                except:
                                    txrec = missingTx

                                # Combine all records and write to table
                                newrec = [mukey]
                                newrec.extend(mrec)
                                newrec.extend(corec)
                                newrec.extend(hzrec)
                                newrec.extend(txrec)
                                ocur.insertRow(newrec)

                        except KeyError:
                            # No horizon records for this component
                            comppct = corec[1]
                            compname = corec[3]
                            compkind = corec[4]
                            mjrcomp = corec[2]
                            #PrintMsg("Major compflag = " + str(corec), 1)

                            hzrec = missingHz
                            txrec = missingTx
                            newrec = [mukey]
                            newrec.extend(mrec)
                            newrec.extend(corec)
                            newrec.extend(hzrec)
                            newrec.extend(txrec)
                            ocur.insertRow(newrec)

                            if not (compname in ["NOTCOM", "NOTPUB"] or compkind == 'Miscellaneous area'):
                                badComp = [mukey, str(cokey), compname, compkind, mjrcomp, str(comppct)]
                                coNoHz.append(str(cokey))   # add cokey to list of components with no horizon data
                                dNoHz[cokey] = badComp      # add component information to dictionary
                                #PrintMsg(" \nMissing horizon data: " + str(corec), 1)

                        except:
                            PrintMsg(" \nhzVals error for " + str(mukey) + ":" + str(cokey) + ": " + str(txrec), 2)
                            PrintMsg(" \n" + str(fldAll2), 1)
                            errorMsg()

                except:
                    # No component records for this map unit
                    corec = missingCo
                    hzrec = missingHz
                    txrec = missingTx
                    newrec = [mukey]
                    newrec.extend(mrec)
                    newrec.extend(corec)
                    newrec.extend(hzrec)
                    newrec.extend(txrec)
                    ocur.insertRow(newrec)

                    if not  mrec[0] in ['NOTCOM', 'NOTPUB']:
                        # skip map units that should never have component data
                        #
                        muNoCo.append(str(mukey))
                        dNoCo[str(mukey)] = [mrec[0], mrec[1]] # Save map unit name for the report
                        #PrintMsg(" \n\n** No component data for " + str(mrec[1]), 2)

        del dMu, dCo


        # Run through QueryTbl_HZ table, checking for inconsistencies in horizon depths
        # Create a dictionary containing a list of top and bottom of each horizon in each component
        # dictionary key = cokey
        # list contains tuples of hzdept_r, hzdepb_r, hzname, mukey, compname, localphase

        dHZ = dict()

        # Exclude horizon data with null hzdep with whereclause
        wc = "hzdept_r is not null and hzdepb_r is not null"
        arcpy.ResetProgressor()
        arcpy.SetProgressorLabel("Looking for inconsistencies in horizon depths...")

        #PrintMsg(" \nWriting component restrictions to " + outputCR, 0)
        arcpy.SetProgressor ("step", "Writing component restriction data to " + outputCR + "...", 0, len(dCr), 1)

        with arcpy.da.InsertCursor(outputCR, fldCr2) as ocur:
            for cokey, crrec in dCr.items():
                ocur.insertRow(crrec)

        env.workspace = outputDB
        del dCr
        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CreateOutputTableMu(theMuTable, depthList, dPct):
    # Create the Valu1 table (theMuTable). Probably should rename this variable.
    #
    try:
        # Create the output tables and add required fields

        try:
            # Try to handle existing output table if user has added it to ArcMap from a previous run
            if arcpy.Exists(theMuTable):
                arcpy.Delete_management(theMuTable)

        except:
            raise MyError, "Previous output table (" + theMuTable + ") is in use and cannot be removed"
            return False

        #PrintMsg(" \nCreating new output table (" + os.path.basename(theMuTable) + ") for mapunit level data", 0)
        outputDB = os.path.dirname(theMuTable)
        tmpTable = os.path.join("IN_MEMORY", os.path.basename(theMuTable))

        #arcpy.CreateTable_management(outputDB, os.path.basename(theMuTable))
        arcpy.CreateTable_management("IN_MEMORY", os.path.basename(theMuTable))

        # Add fields for AWS
        for rng in depthList:
            # Create the AWS fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            awsField = "aws" + str(td) + "_" + str(bd)
            arcpy.AddField_management(tmpTable, awsField, "FLOAT", "", "", "", awsField)  # Integer is more appropriate

        for rng in depthList:
            # Create the AWS fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            awsField = "tk" + str(td) + "_" + str(bd) + "a"
            arcpy.AddField_management(tmpTable, awsField, "FLOAT", "", "", "", awsField)

        arcpy.AddField_management(tmpTable, "musumcpcta", "SHORT", "", "", "")


        # Add Fields for SOC
        for rng in depthList:
            # Create the SOC fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            socField = "soc" + str(td) + "_" + str(bd)
            arcpy.AddField_management(tmpTable, socField, "FLOAT", "", "", "", socField)  # Integer is more appropriate

        for rng in depthList:
            # Create the SOC thickness fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            socField = "tk" + str(td) + "_" + str(bd) + "s"
            arcpy.AddField_management(tmpTable, socField, "FLOAT", "", "", "", socField)

        arcpy.AddField_management(tmpTable, "musumcpcts", "SHORT", "", "", "")

        if mainRuleName == "NCCPI - National Commodity Crop Productivity Index (Ver 2.0)":
            # Add fields for NCCPI version 2
            #
            arcpy.AddField_management(tmpTable, "nccpi2cs", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi2sg", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi2co", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi2all", "FLOAT", "", "", "")

        elif mainRuleName == "NCCPI - National Commodity Crop Productivity Index (Ver 3.0)":
            # Add fields for NCCPI version 3
            #  "mukey", "NCCPI2CORN", "NCCPI2SOY", "NCCPI2COT","NCCPI2SG", "NCCPI2ALL"
            arcpy.AddField_management(tmpTable, "nccpi3corn", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi3soy", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi3cot", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi3sg", "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "nccpi3all", "FLOAT", "", "", "")

        else:
            #PrintMsg(" \n\tNeither NCCPI version 2 or 3 not found", 1)
            raise MyError, "Problem handling mainrule: " + mainRuleName

        # Add fields for root zone depth and root zone available water supply
        arcpy.AddField_management(tmpTable, "pctearthmc", "SHORT", "", "", "")
        arcpy.AddField_management(tmpTable, "rootznemc", "SHORT", "", "", "")
        arcpy.AddField_management(tmpTable, "rootznaws", "SHORT", "", "", "")
        # Add field for droughty soils
        arcpy.AddField_management(tmpTable, "droughty", "SHORT", "", "", "")

        # Add field for potential wetland soils
        arcpy.AddField_management(tmpTable, "pwsl1pomu", "SHORT", "", "", "")

        # Add field for mapunit-sum of ALL component-comppct_r values
        arcpy.AddField_management(tmpTable, "musumcpct", "SHORT", "", "", "")

        # Add Mukey field (primary key)
        arcpy.AddField_management(tmpTable, "mukey", "TEXT", "", "", "30", "mukey")

        # Convert IN_MEMORY table to a permanent table
        arcpy.CreateTable_management(outputDB, os.path.basename(theMuTable), tmpTable)
        # Add attribute indexes for key fields
        arcpy.AddIndex_management(theMuTable, "MUKEY", "Indx_ResMukey", "NON_UNIQUE", "NON_ASCENDING")

        arcpy.Delete_management(os.path.join("IN_MEMORY", os.path.basename(theMuTable)))

        # Reading from the original mapunit table, populate the output Valu1 table with mukey and musumpct
        #PrintMsg(" \n\tPopulating " + theMuTable + " with mukey values", 1)
        with arcpy.da.SearchCursor(os.path.join(outputDB, "mapunit"), ["mukey"]) as incur:
            outcur = arcpy.da.InsertCursor(theMuTable, ["mukey", "musumcpct"])
            for inrec in incur:
                mukey = inrec[0]
                try:
                    sumPct = dPct[mukey][0]

                except:
                    sumPct = 0
                inrec = [mukey, sumPct]
                outcur.insertRow(inrec)

        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CreateOutputTableCo(theCompTable, depthList):
    # Create the Co_Valu component level table (theCompTable). Probably should rename that variable.
    # The new input field is created using adaptive code from another script.
    #
    try:
        # Create two output tables and add required fields
        try:
            # Try to handle existing output table if user has added it to ArcMap from a previous run
            if arcpy.Exists(theCompTable):
                arcpy.Delete_management(theCompTable)

        except:
            raise MyError, "Previous output table (" + theCompTable + ") is in use and cannot be removed"
            return False

        #PrintMsg(" \nCreating new output table (" + os.path.basename(theCompTable) + ") for component level data", 0)

        outputDB = os.path.dirname(theCompTable)
        tmpTable = os.path.join("IN_MEMORY", os.path.basename(theCompTable))

        arcpy.CreateTable_management("IN_MEMORY", os.path.basename(theCompTable))

        # Add fields appropriate for the component level restrictions
        # mukey,cokey, compName, localphase, compPct, comppct, resdept, restriction

        arcpy.AddField_management(tmpTable, "COKEY", "TEXT", "", "", "30", "COKEY")
        arcpy.AddField_management(tmpTable, "COMPNAME", "TEXT", "", "", "60", "COMPNAME")
        arcpy.AddField_management(tmpTable, "LOCALPHASE", "TEXT", "", "", "40", "LOCALPHASE")
        arcpy.AddField_management(tmpTable, "COMPPCT_R", "SHORT", "", "", "", "COMPPCT_R")

        for rng in depthList:
            # Create the AWS fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            awsField = "AWS" + str(td) + "_" + str(bd)
            arcpy.AddField_management(tmpTable, awsField, "FLOAT", "", "", "", awsField)


        for rng in depthList:
            # Create the AWS fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            awsField = "TK" + str(td) + "_" + str(bd) + "A"
            arcpy.AddField_management(tmpTable, awsField, "FLOAT", "", "", "", awsField)

        arcpy.AddField_management(tmpTable, "MUSUMCPCTA", "SHORT", "", "", "")

        for rng in depthList:
            # Create the SOC fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            awsField = "SOC" + str(td) + "_" + str(bd)
            arcpy.AddField_management(tmpTable, awsField, "FLOAT", "", "", "")

        for rng in depthList:
            # Create the rest of the SOC thickness fields in a loop
            #
            td = rng[0]
            bd = rng[1]
            awsField = "TK" + str(td) + "_" + str(bd) + "S"
            arcpy.AddField_management(tmpTable, awsField, "FLOAT", "", "", "")
            arcpy.AddField_management(tmpTable, "MUSUMCPCTS", "SHORT", "", "", "")

        # Root Zone and root zone available water supply
        arcpy.AddField_management(tmpTable, "PCTEARTHMC", "SHORT", "", "", "")
        arcpy.AddField_management(tmpTable, "ROOTZNEMC", "SHORT", "", "", "")
        arcpy.AddField_management(tmpTable, "ROOTZNAWS", "SHORT", "", "", "")
        arcpy.AddField_management(tmpTable, "RESTRICTION", "TEXT", "", "", "254", "RESTRICTION")

        # Droughty soils
        arcpy.AddField_management(tmpTable, "DROUGHTY", "SHORT", "", "", "")

        # Add field for potential wetland soils
        arcpy.AddField_management(tmpTable, "PWSL1POMU", "SHORT", "", "", "")

        # Add primary key field
        arcpy.AddField_management(tmpTable, "MUKEY", "TEXT", "", "", "30", "MUKEY")

        # Convert IN_MEMORY table to a permanent table
        if arcpy.Exists(os.path.join(outputDB, os.path.basename(theCompTable))):
            arcpy.Delete_management(os.path.join(outputDB, os.path.basename(theCompTable)))

        arcpy.CreateTable_management(outputDB, os.path.basename(theCompTable), tmpTable)

        # add attribute indexes for key fields
        arcpy.AddIndex_management(theCompTable, "MUKEY", "Indx_Res2Mukey", "NON_UNIQUE", "NON_ASCENDING")
        arcpy.AddIndex_management(theCompTable, "COKEY", "Indx_ResCokey", "UNIQUE", "NON_ASCENDING")

        # populate table with mukey values
        #PrintMsg(" \n\tPopulating " + theCompTable + " with basic component values", 1)
        with arcpy.da.SearchCursor(os.path.join(outputDB, "component"), ["mukey", "cokey", "compname", "localphase", "comppct_r"]) as incur:
            outcur = arcpy.da.InsertCursor(theCompTable, ["mukey", "cokey", "compname", "localphase", "comppct_r"])
            for inrec in incur:
                outcur.insertRow(inrec)

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False


## ===================================================================================
def CheckTexture(mukey, cokey, desgnmaster, om, texture, lieutex, taxorder, taxsubgrp):
    # Is this an organic horizon? Look at desgnmaster and OM first. If those
    # don't help, look at chtexturegrp.texture next.
    #
    # if True: Organic, exclude from root zone calculations unless it is 'buried'
    # if False: Mineral, include in root zone calculations
    #
    # 01-26-2015
    #
    # According to Bob, if TAXORDER = 'Histosol' and DESGNMASTER = 'O' or 'L' then it should NOT be included in the RZAWS calculations
    #
    # If desgnmast = 'O' or 'L' and not (TAXORDER = 'Histosol' OR TAXSUBGRP like 'Histic%') then exclude this horizon from all RZAWS calcualtions.
    #
    # lieutex values: Slightly decomposed plant material, Moderately decomposed plant material,
    # Bedrock, Variable, Peat, Material, Unweathered bedrock, Sand and gravel, Mucky peat, Muck,
    # Highly decomposed plant material, Weathered bedrock, Cemented, Gravel, Water, Cobbles,
    # Stones, Channers, Parachanners, Indurated, Cinders, Duripan, Fragmental material, Paragravel,
    # Artifacts, Boulders, Marl, Flagstones, Coprogenous earth, Ashy, Gypsiferous material,
    # Petrocalcic, Paracobbles, Diatomaceous earth, Fine gypsum material, Undecomposed organic matter

    # According to Bob, any of these 'decomposed plant material', 'Muck, 'Mucky peat, 'Peat', 'Coprogenous earth' LIEUTEX
    # values qualify.
    #
    # This function does not determine whether the horizon might be a buried organic. That is done in CalcRZAWS1.
    #

    lieuList = ['Slightly decomposed plant material', 'Moderately decomposed plant material', \
    'Highly decomposed plant material', 'Undecomposed plant material', 'Muck', 'Mucky peat', \
    'Peat', 'Coprogenous earth']
    txList = ["CE", "COP-MAT", "HPM", "MPM", "MPT", "MUCK", "PDOM", "PEAT", "SPM", "UDOM"]

    try:

        if str(taxorder) == 'Histosols' or str(taxsubgrp).lower().find('histic') >= 0:
            # Always treat histisols and histic components as having all mineral horizons
            #if mukey == tmukey:
            #    PrintMsg("\tHistisol or histic: " + cokey + ", " + str(taxorder) + ", " + str(taxsubgrp), 1)
            return False

        elif desgnmaster in ["O", "L"]:
            # This is an organic horizon according to CHORIZON.DESGNMASTER OR OM_R
            #if mukey == tmukey:
            #    PrintMsg("\tO: " + cokey + ", " + str(taxorder) + ", " + str(taxsubgrp), 1)
            return True

        #elif om > 19:
            # This is an organic horizon according to CHORIZON.DESGNMASTER OR OM_R
        #    if mukey == tmukey:
        #        PrintMsg("\tHigh om_r: " + cokey + ", " + str(taxorder) + ", " + str(taxsubgrp), 1)
        #    return True

        elif str(texture) in txList:
            # This is an organic horizon according to CHTEXTUREGRP.TEXTURE
            #if mukey == tmukey:
            #    PrintMsg("\tTexture: " + cokey + ", " + str(taxorder) + ", " + str(taxsubgrp), 1)
            return True

        elif str(lieutex) in lieuList:
            # This is an organic horizon according to CHTEXTURE.LIEUTEX
            #if mukey == tmukey:
            #    PrintMsg("\tLieutex: " + cokey + ", " + str(taxorder) + ", " + str(taxsubgrp), 1)
            return True

        else:
            # Default to mineral horizon if it doesn't match any of the criteria
            #if mukey == tmukey:
            #    PrintMsg("\tDefault mineral: " + cokey + ", " + str(taxorder) + ", " + str(taxsubgrp), 1)
            return False

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CheckBulkDensity(sand, silt, clay, bd, mukey, cokey):
    # Bob's check for a dense layer
    # If sand, silt or clay are missing then we default to Dense layer = False
    # If the sum of sand, silt, clay are less than 100 then we default to Dense layer = False
    # If a single sand, silt or clay value is NULL, calculate it

    try:

        #if mukey == tmukey:
        #    PrintMsg("\tCheck for Dense: " + str(mukey) + ", " + str(cokey) + ", " + \
        #    str(sand) + ", " + str(silt) + ", " + str(clay) + ", " + str(bd), 1)

        txlist = [sand, silt, clay]

        if bd is None:
            # This is not a Dense Layer
            #if mukey == tmukey:
            #    PrintMsg("\tMissing bulk density", 1)
            return False

        if txlist.count(None) == 1:
            # Missing a single total_r value, calculate it
            if txlist[0] is None:
                sand = 100.0 - silt - clay

            elif silt is None:
                silt = 100.0 - sand - clay

            else:
                clay = 100.0 - sand - silt

            txlist = [sand, silt, clay]

        if txlist.count(None) > 0:
            # Null values for more than one, return False
            #if mukey == tmukey:
            #    PrintMsg("\tDense layer with too many null texture values", 1)
            return False

        if round(sum(txlist), 1) <> 100.0:
            # Cannot run calculation, default value is False
            #if mukey == tmukey:
            #    PrintMsg("\tTexture values do not sum to 100", 1)
            return False

        # All values required to run the Dense Layer calculation are available

        a = bd - ((( sand * 1.65 ) / 100.0 ) + (( silt * 1.30 ) / 100.0 ) + (( clay * 1.25 ) / 100.0))

        b = ( 0.002081 * sand ) + ( 0.003912 * silt ) + ( 0.0024351 * clay )

        if a > b:
            # This is a Dense Layer
            #if mukey == tmukey:
            #    PrintMsg("\tDense layer: a = " + str(a) + " and   b = " + str(b) + " and BD = " + str(bd), 1)

            return True

        else:
            # This is not a Dense Layer
            #if mukey == tmukey:
            #    PrintMsg("\tNot a Dense layer: a = " + str(a) + " and   b = " + str(b) + " and BD = " + str(bd), 1)

            return False

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CalcRZDepth(inputDB, outputDB, theCompTable, theMuTable, maxD, dPct, dCR):
    #
    # Look at soil horizon properties to adjust the root zone depth.
    # This is in addition to the standard component restrictions
    #
    # Read the component restrictions into a dictionary, then read through the
    # QueryTable_Hz table, calculating the final component rootzone depth
    #
    # Components with COMPKIND = 'Miscellaneous area' or NULL are filtered out.
    # Components with no horizon data are assigned a root zone depth of zero.
    #
    # Horizons with NULL hzdept_r or hzdepb_r are filtered out
    # Horizons with hzdept_r => hzdepb_r are filtered out
    # O horizons or organic horizons from the surface down to the first mineral horizon
    # are filtered out.
    #
    # Horizon data below 150cm or select component restrictions are filtered out.
    # A Dense layer calculation is also included as an additional horizon-specific restriction.

    try:
        dComp = dict()      # component level data for all component restrictions
        dComp2 = dict()     # store all component level data plus default values
        coList = list()

        #bInput = CreateQueryTables1(inputDB, outputDB)
        queryTbl = os.path.join(outputDB, "QueryTable_Hz")

        #if bInput == False:
        #    raise MyError, "Problem querying input database"

        #PrintMsg(" \nProcessing input table (" + queryTbl + ")")

        # Create dictionaries and lists
        dMapunit = dict()   # store mapunit weighted restriction depths

        # FIELDS LIST FOR INPUT TABLE
        # areasymbol, mukey, musym, muname, mukname,
        # cokey, compct, compname, compkind, localphase,
        # taxorder, taxsubgrp, ec, pH, dbthirdbar, hzname,
        # hzdesgn, hzdept, hzdepb, hzthk, sand,
        # silt, clay, om, reskind, reshard,
        # resdept, resthk, texture, lieutex

        # All reskind values: Strongly contrasting textural stratification, Lithic bedrock, Densic material,
        # Ortstein, Permafrost, Paralithic bedrock, Cemented horizon, Undefined, Fragipan, Plinthite,
        # Abrupt textural change, Natric, Petrocalcic, Duripan, Densic bedrock, Salic,
        # Human-manufactured materials, Sulfuric, Placic, Petroferric, Petrogypsic
        #
        # Using these restrictions:
        # Lithic bedrock, Paralithic bedrock, Densic bedrock, Fragipan, Duripan, Sulfuric

        # Other restrictions include pH < 3.5 and EC > 16

        resTbl = os.path.join(outputDB, "QueryTable_CR")
        crFlds = ["cokey","reskind", "reshard", "resdept_r"]
        sqlClause = (None, "ORDER BY cokey, resdept_r ASC")

        # ********************************************************
        #
        # Read the QueryTable_HZ and adjust the component restrictions for additional
        # issues such as pH, EC, etc.
        #
        # Save these new restriction values to dComp dictionary
        #
        # Only process major-earthy components...
        whereClause = "component.compkind <> 'Miscellaneous area' and component.compkind is not Null and component.majcompflag = 'Yes'"

        sqlClause = (None, "ORDER BY mukey, comppct_r DESC, cokey, hzdept_r ASC")
        curFlds = ["mukey", "cokey", "compname", "compkind", "localphase", "comppct_r", "taxorder", "taxsubgrp", "hzname", "desgnmaster", "hzdept_r", "hzdepb_r", "sandtotal_r", "silttotal_r", "claytotal_r", "om_r", "dbthirdbar_r", "ph1to1h2o_r", "ec_r", "awc_r", "texture", "lieutex"]
        resList = ['Lithic bedrock','Paralithic bedrock','Densic bedrock', 'Fragipan', 'Duripan', 'Sulfuric']

        lastCokey = "xxxx"
        lastMukey = 'xxxx'

        # Display status of processing input table containing horizon data and component restrictions
        inCnt = int(arcpy.GetCount_management(queryTbl).getOutput(0))

        if inCnt > 0:
            arcpy.SetProgressor ("step", "Processing input table...", 0, inCnt, 1)

        else:
            raise MyError, "Input table contains no data"

        with arcpy.da.SearchCursor(queryTbl, curFlds, where_clause=whereClause, sql_clause=sqlClause) as cur:
            # Reading horizon-level data
            for rec in cur:

                # ********************************************************
                #
                # Read QueryTable_HZ record
                mukey, cokey, compName, compKind, localPhase, compPct, taxorder, taxsubgrp, hzname, desgnmaster, hzDept, hzDepb, sand, silt, clay, om, bd, pH, ec, awc, texture, lieutex = rec

                # Initialize component restriction depth to maxD
                dComp2[cokey] = [mukey, compName, localPhase, compPct, maxD, ""]

                if lastCokey != cokey:
                    # Accumulate a list of components for future use
                    lastCokey = cokey
                    coList.append(cokey)

                if hzDept < maxD:
                    # ********************************************************
                    # For horizons above the floor level (maxD), look for other restrictive
                    # layers based on horizon properties such as pH, EC and bulk density.
                    # Start with the top horizons and work down.

                    # initialize list of restrictions
                    resKind = ""
                    restriction = list()

                    bOrganic = CheckTexture(mukey, cokey, desgnmaster, om, texture, lieutex, taxorder, taxsubgrp)

                    if not bOrganic:
                        # calculate alternate dense layer per Dobos
                        bDense = CheckBulkDensity(sand, silt, clay, bd, mukey, cokey)

                        if bDense:
                            # use horizon top depth for the dense layer
                            restriction.append("Dense")
                            resDept = hzDept

                        # Not sure whether these horizon property checks should be skipped for Organic
                        # Bob said to only skip Dense Layer check, but VALU table RZAWS looks like all
                        # horizon properties were skipped.
                        #
                        # If we decide to skip EC and pH horizon checks for histosols/histic, use this query
                        # Example Pongo muck in North Carolina that have low pH but no other restriction
                        #
                        if str(taxorder) != 'Histosols' and str(taxsubgrp).lower().find('histic') == -1:
                            # Only non histosols/histic soils will be checked for pH or EC restrictive horizons
                            if pH <= 3.5 and pH is not None:
                                restriction.append("pH")
                                resDept = hzDept
                                #if mukey == tmukey:
                                #    PrintMsg("\tpH restriction at " + str(resDept) + "cm", 1)

                        if ec >= 16.0 and ec is not None:
                            # Originally I understood that EC > 12 is a restriction, but Bob says he is
                            # now using 16.
                            restriction.append("EC")
                            resDept = hzDept
                            #if mukey == tmukey:
                            #    PrintMsg("\tEC restriction at " + str(resDept) + "cm", 1)

                        #if bd >= 1.8:
                        #    restriction.append("BD")
                        #    resDept = hzDept

                        #if awc is None:
                        #    restriction.append("AWC")
                        #    resDept = hzDept

                    # ********************************************************
                    #
                    # Finally, check for one of the standard component restrictions
                    #
                    if cokey in dCR:
                        resDepth2, resKind = dCR[cokey]

                        if hzDept <= resDepth2 < hzDepb:
                            # This restriction may not be at the top of the horizon, thus we
                            # need to override this if one of the other restrictions exists for this
                            # horizon

                            if len(restriction) == 0:
                                # If this is the only restriction, set the restriction depth
                                # to the value from the corestriction table.
                                resDept = resDepth2

                            # Adding this restriction name to the list even if there are others
                            # May want to take this out later
                            restriction.append(resKind)

                    # ********************************************************
                    #
                    if len(restriction) > 0:
                        # Found at least one restriction for this horizon

                        if not cokey in dComp:
                            # if there are no higher restrictions for this component, save this one
                            # to the dComp dictionary as the top-most restriction
                            #
                            dComp[cokey] = [mukey, compName, localPhase, compPct, resDept, restriction]

                arcpy.SetProgressorPosition()

        arcpy.ResetProgressor()

        # Load restrictions from dComp into dComp2 so that there is complete information for all components

        for cokey in dComp2:
            try:
                dComp2[cokey] = dComp[cokey]

            except:
                pass

        # Return the dictionary containing restriction depths and the dictionary containing defaults
        return dComp2

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return dComp2

    except:
        errorMsg()
        return dComp2


## ===================================================================================
def GetCoRestrictions(outputDB, maxD, resList):
    #
    # Returns a dictionary of top component restrictions for root growth
    #
    # resList is a comma-delimited string of reskind values, surrounded by parenthesis
    #
    # Get component root zone depth from QueryTable_CR and load into dictionary (dCR)
    # This is NOT the final root zone depth. This information will be compared with the
    # horizon soil properties to determine the final root zone depth.

    try:
        rSQL = "resdept_r < " + str(maxD) + " and reskind in " + resList
        sqlClause = (None, "ORDER BY cokey, resdept_r ASC")
        resTbl = os.path.join(outputDB, "QueryTable_CR")
        #PrintMsg("\tGetting corestrictions matching: " + resList, 1)

        if not arcpy.Exists(resTbl):
            raise MyError, "Missing required input table (" + resTbl + ")"

        dRestrictions = dict()

        # Get the top component restriction from the sorted table
        with arcpy.da.SearchCursor(resTbl, ["cokey", "resdept_r", "reskind"], where_clause=rSQL, sql_clause=sqlClause) as cur:
            for rec in cur:
                cokey, resDept, reskind = rec
                #PrintMsg("Restriction: " + str(rec), 1)

                if not cokey in dRestrictions:
                    dRestrictions[cokey] = resDept, reskind
                    #PrintMsg(cokey + ", " + str(resDept) + ", " + reskind, 1)

        return dRestrictions

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return dict()

    except:
        errorMsg()
        return dict()


## ===================================================================================
def CalcRZAWS(inputDB, outputDB, td, bd, theCompTable, theMuTable, dRestrictions, maxD, dPct):
    # Create a component-level summary table
    # Calculate mapunit-weighted average for each mapunit and write to a mapunit-level table
    # Need to filter out compkind = 'Miscellaneous area' for RZAWS
    # dRestrictions[cokey] = [mukey, compName, localPhase, compPct, resDept, restriction]

    try:
        import decimal

        env.workspace = outputDB

        # Using the same component horizon table that has been
        queryTbl = os.path.join(outputDB, "QueryTable_Hz")

        numRows = int(arcpy.GetCount_management(queryTbl).getOutput(0))

        PrintMsg(" \n\tCalculating Root Zone AWS for " + str(td) + " to " + str(bd) + "cm...", 0)

        # QueryTable_HZ fields
        qFieldNames = ["mukey", "cokey", "comppct_r",  "compname", "localphase", "majcompflag", "compkind", "taxorder", "taxsubgrp", "desgnmaster", "om_r", "awc_r", "hzdept_r", "hzdepb_r", "texture", "lieutex"]

        #arcpy.SetProgressorLabel("Creating output tables using dominant component...")
        #arcpy.SetProgressor("step", "Calculating root zone available water supply..." , 0, numRows, 1)

        # Open edit session on geodatabase to allow multiple update cursors
        with arcpy.da.Editor(inputDB) as edit:

            # initialize list of components with horizon overlaps
            #badCo = list()

            # Output fields for root zone and droughty
            muFieldNames = ["mukey", "pctearthmc", "rootznemc", "rootznaws", "droughty"]
            muCursor = arcpy.da.UpdateCursor(theMuTable, muFieldNames)

            # Open component-level output table for updates
            #coCursor = arcpy.da.InsertCursor(theCompTable, coFieldNames)
            coFieldNames = ["mukey", "cokey", "compname", "localphase", "comppct_r", "pctearthmc", "rootznemc", "rootznaws", "restriction"]
            coCursor = arcpy.da.UpdateCursor(theCompTable, coFieldNames)

            # Process query table using cursor, write out horizon data for each major component
            sqlClause = [None, "order by mukey, comppct_r DESC, cokey, hzdept_r ASC"]
            iCnt = int(arcpy.GetCount_management(queryTbl).getOutput(0))

            # For root zone calculations, we only want earthy, major components
            #PrintMsg(" \nFiltering components in Query_HZ for CalcRZAWS1 function", 1)
            #
            # Major-Earthy Components
            #hzSQL = "component.compkind <> 'Miscellaneous area' and component.compkind is not NULL and component.majcompflag = 'Yes'"
            # All Components

            inCur = arcpy.da.SearchCursor(queryTbl, qFieldNames, sql_clause=sqlClause)

            arcpy.SetProgressor("step", "Reading query table...",  0, iCnt, 1)

            # Create dictionaries to handle the mapunit and component summaries
            dMu = dict()
            dComp = dict()

            # I may have to pull the sum of component percentages out of this function?
            # It seems to work OK for the earthy-major components, but will not work for
            # the standard AWS calculations. Those 'Miscellaneous area' components with no horizon data
            # are excluded from the Query table because it does not support Outer Joins.
            #
            mCnt = 0
            #PrintMsg("\tmukey, cokey, comppct, top, bottom, resdepth, thickness, aws", 0)

            # TEST: keep list of cokeys as a way to track the top organic horizons
            skipList = list()

            for rec in inCur:
                # read each horizon-level input record from QueryTable_HZ ...
                #
                mukey, cokey, compPct, compName, localPhase, mjrFlag, cKind, taxorder, taxsubgrp, desgnmaster, om, awc, top, bot, texture, lieutex = rec

                if mjrFlag == "Yes" and cKind != "Miscellaneous area" and cKind is not None:

                    # For major-earthy components
                    # Get restriction information from dictionary

                    # For non-Miscellaneous areas with no horizon data, set hzdepth values to zero so that
                    # PWSL and Droughty will get populated with zeros instead of NULL.
                    if top is None and bot is None:

                        if not cokey in dComp:
                            dComp[cokey] = mukey, compName, localPhase, compPct, 0, 0, ""

                    try:
                        # mukey, compName, localPhase, compPct, resDept, restriction
                        # rDepth is the component restriction depth or calculated horizon restriction from CalcRZDepth1 function

                        # mukey, compName, localPhase, compPct, resDept, restriction] = dRestrictions
                        d1, d2, d3, d4, rDepth, restriction = dRestrictions[cokey]
                        cBot = min(rDepth, bot, maxD)  # 01-05-2015 Added maxD because I found 46 CONUS mapunits with a ROOTZNEMC > 150

                        #if mukey == tmukey and rDepth != 150:
                        #    PrintMsg("\tRestriction, " + str(mukey) + ", " + str(cokey) + ", " + str(rDepth) + ", " + str(restriction), 1)

                    except:
                        #errorMsg()
                        cBot = min(maxD, bot)
                        restriction = []
                        rDepth = maxD

                        #if mukey == tmukey:
                        #    PrintMsg("RestrictionError, " + str(mukey) + ", " + str(cokey) + ", " + str(rDepth) + ", " + str(restriction), 1)

                    bOrganic = CheckTexture(mukey, cokey, desgnmaster, om, texture, lieutex, taxorder, taxsubgrp)

                    #if mukey == tmukey and bOrganic:
                    #    PrintMsg("Organic: " + str(mukey) + ", " + str(cokey) )


                    # fix awc_r to 2 decimal places
                    if awc is None:
                        awc = 0.0

                    else:
                        awc = round(awc, 2)

                    # Reasons for skipping RZ calculations on a horizon:
                    #   1. Desgnmaster = O, L and Taxorder != Histosol and is at the surface
                    #   2. Do I need to convert null awc values to zero?
                    #   3. Below component restriction or horizon restriction level

                    if bOrganic and not cokey in skipList:
                        # Organic surface horizon - Not using this horizon in the calculations
                        useHz = False

                        #if mukey == tmukey:
                        #    PrintMsg("Organic, " + str(mukey) + ", " + str(cokey) + ", " + str(compPct) + ", " + str(desgnmaster) + ", " + taxorder  + ", " + str(top) + ", " + str(bot) + ", " + str(cBot)  + ", " + str(awc) + ", " + str(useHz), 1)

                    else:
                        # Mineral, Histosol, buried Organic, Bedrock or there is a horizon restriction (EC, pH - Using this horizon in the calculations
                        useHz = True
                        skipList.append(cokey)

                        # Looking for problems
                        #if mukey == tmukey:
                        #    PrintMsg("Mineral, " + str(mukey) + ", " + str(cokey)  + ", " + str(compPct) + ", " + str(desgnmaster) + ", " + str(taxorder) + ", " + str(top) + ", " + str(bot) + ", " + str(cBot) + ", " + str(awc)  + ", " + str(useHz), 1)

                        # Attempt to fix component with a surface-level restriction that might be in an urban soil
                        if not cokey in dComp and cBot == 0:
                            dComp[cokey] = mukey, compName, localPhase, compPct, 0, 0, restriction

                            # Looking for problems
                            #if mukey == tmukey:
                            #    PrintMsg("MUKEY2: " + str(mukey) + ", " + str(top) + ", " + str(bot) + ", " + str(cBot) + ", " + str(useHz), 1)

                    if top < cBot and useHz == True:
                        # If the top depth is less than the bottom depth, proceed with the calculation
                        # Calculate sum of horizon thickness and sum of component ratings for all horizons above bottom
                        hzT = cBot - top
                        aws = float(hzT) * float(awc) * 10.0

                        # Looking for problems
                        #if mukey == tmukey:
                        #    PrintMsg("MUKEY3: " + str(mukey) + ", " + str(top) + ", " + str(bot) + ", " + str(cBot) + ", " + str(useHz), 1)


                        if cokey in dComp:
                            # accumulate total thickness and total rating value by adding to existing component values
                            mukey, compName, localPhase, compPct, dHzT, dAWS, restriction = dComp[cokey]
                            dAWS = dAWS + aws
                            dHzT += hzT

                            dComp[cokey] = mukey, compName, localPhase, compPct, dHzT, dAWS, restriction

                        else:
                            # Create initial entry for this component using the first horizon
                            dComp[cokey] = mukey, compName, localPhase, compPct, hzT, aws, restriction

                    else:
                        # Do not include this horizon in the rootzone calculations
                        pass

                else:
                    # Not a major-earthy component, so write out everything BUT rzaws-related data (last values)
                    dComp[cokey] = mukey, compName, localPhase, compPct, None, None, None, None

                arcpy.SetProgressorPosition()

                # end of processing major-earthy components

            arcpy.ResetProgressor()

            # get the total number of major-earthy components from the dictionary count
            iComp = len(dComp)

            # Read through the component-level data and summarize to the mapunit level

            if iComp > 0:
                #PrintMsg(" \nSaving component average RZAWS to table... (" + str(iComp) + ")", 0 )
                arcpy.SetProgressor("step", "Saving component data...",  0, iComp, 1)
                iCo = 0 # count component records written to theCompTbl

                for corec in coCursor:
                    mukey, cokey, compName, localPhase, compPct, pctearthmc, rDepth, aws, restrictions = corec

                    try:
                        # get sum of component percent for the mapunit
                        pctearthmc = float(dPct[mukey][1])   # sum of comppct_r for all major components Test 2014-10-07

                        # get rootzone data from dComp
                        mukey1, compName1, localPhase1, compPct1, hzT, awc, restriction = dComp[cokey]

                    except:
                        pctearthmc = 0
                        hzT = None
                        rDepth = None
                        awc = None
                        restriction = []

                    # calculate component percentage adjustment
                    if pctearthmc > 0 and not awc is None:
                        # If there is no data for any of the component horizons, could end up with 0 for
                        # sum of comppct_r

                        adjCompPct = float(compPct) / float(pctearthmc)

                        # adjust the rating value down by the component percentage and by the sum of the usable horizon thickness for this component
                        aws = adjCompPct * float(awc) # component rating

                        if restriction is None:
                            restrictions = ''

                        elif len(restriction) > 0:
                            restrictions = ",".join(restriction)

                        else:
                            restrictions = ''

                        corec = mukey, cokey, compName, localPhase, compPct, pctearthmc, hzT, aws, restrictions

                        coCursor.updateRow(corec)
                        iCo += 1

                        # Weight hzT for ROOTZNEMC by component percent
                        hzT = (float(hzT) * float(compPct) / pctearthmc)

                        if mukey in dMu:
                            val1, val2, val3 = dMu[mukey]
                            dMu[mukey] = pctearthmc, (hzT + val2), (aws + val3)

                        else:
                            # first entry for map unit ratings
                            dMu[mukey] = pctearthmc, hzT, aws

                        # PrintMsg("Mapunit " + mukey + ":" + cokey + "  " + str(dMu[mukey]), 1)

                    else:
                        # Populate component level record for a component with no AWC
                        corec = mukey, cokey, compName, localPhase, compPct, None, None, None, ""
                        coCursor.updateRow(corec)
                        iCo += 1

                    arcpy.SetProgressorPosition()

                arcpy.ResetProgressor()

            else:
                raise MyError, "No component data in dictionary dComp"

            if len(dMu) > 0:
                PrintMsg(" \n\tSaving map unit average RZAWS to table...(" + str(len(dMu)) + ")", 0 )

            else:
                raise MyError, "No map unit information in dictionary dMu"

            # Save root zone available water supply and droughty soils to output map unit table
            #
            for murec in muCursor:
                mukey, pctearthmc, rootznemc, rootznaws, droughty = murec

                try:
                    rec = dMu[mukey]
                    pct, rootznemc, rootznaws = rec
                    pctearthmc = dPct[mukey][1]

                    if rootznemc > 150.0:
                        # This is a bandaid for components that have horizon problems such
                        # overlapping that causes the calculated total to exceed 150cm.
                        rootznemc = 150.0

                    rootznaws = round(rootznaws, 0)
                    rootznemc = round(rootznemc, 0)

                    if rootznaws > 152:
                        droughty = 0

                    else:
                        droughty = 1

                except:
                    pctearthmc = 0
                    rootznemc = None
                    rootznaws = None

                murec = mukey, pctearthmc, rootznemc, rootznaws, droughty
                muCursor.updateRow(murec)

                #if mukey == tmukey:
                    # values at this point seem to be correct
                #    fldnames = muCursor.fields
                #    PrintMsg(str(fldnames), 1)
                #    PrintMsg(str(murec), 1)

            # Save data issues to permanent files for later review
            #if len(badCo) > 0:
            #    fileCo = os.path.basename(inputDB)[:-4] + "_OverlappingHz.txt"
            #    fileCo = os.path.join(os.path.dirname(inputDB), fileCo)
            #    fh = open(fileCo, "w")
            #    fh.write(inputDB + "\n")
            #    fh.write("Components with overlapping horizons\n\n")
            #    fh.write("COKEY IN ('" + "', '".join(badCo) + "') \n")
            #    fh.close()
            #    PrintMsg(" \nComponents with overlapping horizons (" + Number_Format(len(badCo), 0, True) + ") saved to:\t" + fileCo, 0)

            PrintMsg("", 0)

            return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CalcAWS(inputDB, outputDB, theCompTable, theMuTable, dPct, depthList):
    # Create a component-level summary table
    # Calculate the standard mapunit-weighted available waters supply for each mapunit and
    # add it to the map unit-level table.
    #
    # 12-08 I see that for mukey='2479901' my rating is

    try:
        # Using the same component horizon table that has been
        queryTbl = os.path.join(outputDB, "QueryTable_HZ")
        numRows = int(arcpy.GetCount_management(queryTbl).getOutput(0))

        # mukey, cokey, compPct,val, top, bot
        qFieldNames = ["mukey", "cokey", "comppct_r", "awc_r", "hzdept_r", "hzdepb_r"]

        # Track map units that are missing data
        missingList = list()
        minusList = list()

        PrintMsg(" \n\tCalculating standard available water supply for:", 0)

        for rng in depthList:
            # Calculating and updating just one AWS column at a time
            #
            td = rng[0]
            bd = rng[1]
            #outputFields = "AWS" + str(td) + "_" + str(bd), "TK" + str(td) + "_" + str(bd) + "A"

            # Open output table Mu...All in write mode
            muFieldNames = ["MUKEY", "MUSUMCPCTA", "AWS" + str(td) + "_" + str(bd), "TK" + str(td) + "_" + str(bd) + "A"]
            coFieldNames = ["COKEY", "AWS" + str(td) + "_" + str(bd), "TK" + str(td) + "_" + str(bd) + "A"]

            # Create dictionaries to handle the mapunit and component summaries
            dMu = dict()
            dComp = dict()
            dSum = dict()     # store sum of comppct_r and total thickness for the component
            dHz = dict()      # Trying a new dictionary that will s


            arcpy.SetProgressorLabel("Creating output tables using dominant component...")
            arcpy.SetProgressor("step", "Aggregating data for the dominant component..." , 0, numRows, 1)

            # Open edit session on geodatabase to allow multiple insert cursors
            with arcpy.da.Editor(inputDB) as edit:

                # Open output mapunit-level table in update mode
                # MUKEY, AWS
                muCursor = arcpy.da.UpdateCursor(theMuTable, muFieldNames)

                # Open output component-level table in write mode
                # MUKEY, AWS
                coCursor = arcpy.da.UpdateCursor(theCompTable, coFieldNames)

                # Process query table using a searchcursor, write out horizon data for each component
                # At this time, almost all components are being used! There is no filter.
                sqlClause = (None, "order by mukey, comppct_r DESC, cokey, hzdept_r ASC")
                #hzSQL = "compkind is not null and hzdept_r is not null"  # prevent divide-by-zero errors
                hzSQL = "hzdept_r is not null"  # prevent divide-by-zero errors by skipping components with no horizons

                iCnt = int(arcpy.GetCount_management(queryTbl).getOutput(0))
                inCur = arcpy.da.SearchCursor(queryTbl, qFieldNames, where_clause=hzSQL, sql_clause=sqlClause)

                arcpy.SetProgressor("step", "Reading QueryTable_HZ ...",  0, iCnt, 1)

                for rec in inCur:
                    # read each horizon-level input record from the query table ...

                    mukey, cokey, compPct, awc, top, bot = rec

                    if awc is not None:

                        # Calculate sum of horizon thickness and sum of component ratings for all horizons above bottom
                        hzT = min(bot, bd) - max(top, td)   # usable thickness from this horizon

                        if hzT > 0:
                            aws = float(hzT) * float(awc) * 10

                            if not cokey in dComp:
                                # Create initial entry for this component using the first horiozon CHK
                                dComp[cokey] = (mukey, compPct, hzT, aws)

                            else:
                                # accumulate total thickness and total rating value by adding to existing component values  CHK
                                mukey, compName, dHzT, dAWS = dComp[cokey]
                                dAWS = dAWS + aws
                                dHzT = dHzT + hzT
                                dComp[cokey] = (mukey, compPct, dHzT, dAWS)

                    arcpy.SetProgressorPosition()

                # get the total number of major components from the dictionary count
                iComp = len(dComp)

                # Read through the component-level data and summarize to the mapunit level

                if iComp > 0:
                    PrintMsg("\t\t" + str(td) + " - " + str(bd) + "cm (" + Number_Format(iComp, 0, True) + " components)"  , 0)
                    arcpy.SetProgressor("step", "Saving map unit and component AWS data...",  0, iComp, 1)

                    for corec in coCursor:
                        # get component level data  CHK
                        cokey = corec[0]

                        if cokey in dComp:
                            dRec = dComp[cokey]
                            mukey, compPct, hzT, awc = dRec

                            # get sum of component percent for the mapunit  CHK
                            try:
                                # Value[0] is for all components,
                                # Value[1] is just for major-earthy components,
                                # Value[2] is all major components
                                # Value[3] is earthy components
                                sumCompPct = float(dPct[mukey][0])
                                #sumCompPct = float(dPct[mukey][1])

                            except:
                                # set the component percent to zero if it is not found in the
                                # dictionary. This is probably a 'Miscellaneous area' not included in the  CHK
                                # data or it has no horizon information.
                                sumCompPct = 0
                                #missingList.append("'" + mukey + "'")

                            # calculate component percentage adjustment
                            if sumCompPct > 0:
                                # If there is no data for any of the component horizons, could end up with 0 for
                                # sum of comppct_r
                                #PrintMsg(" \nMUKEY " + mukey + " - " + compName + " has zero percent Sum Comppct", 1)


                                #adjCompPct = float(compPct) / sumCompPct   # WSS method
                                adjCompPct = compPct / 100.0                # VALU table method

                                # adjust the rating value down by the component percentage and by the sum of the usable horizon thickness for this component
                                aws = round((adjCompPct * awc), 2) # component rating

                                corec[1] = aws
                                hzT = hzT * adjCompPct    # Adjust component share of horizon thickness by comppct
                                corec[2] = hzT             # This is new for the TK0_5A column
                                coCursor.updateRow(corec)

                                # Update component values in component dictionary   CHK
                                # Not sure what dComp is being used for ???
                                dComp[cokey] = mukey, compPct, hzT, aws

                                # Try to fix high mapunit aggregate HZ by weighting with comppct

                                # Testing new mapunit aggregation 09-08-2014
                                # Trying to replace dMu dictionary
                                if mukey in dMu:
                                    val1, val2, val3 = dMu[mukey]
                                    #dMu[mukey] = (compPct + val1, hzT + val2, aws + val2)
                                    compPct = compPct + val1
                                    hzT = hzT + val2
                                    aws = aws + val3

                                #else:
                                dMu[mukey] = (compPct, hzT, aws)
                                #PrintMsg("\tAWS for " + mukey + ": " + str(dMu[mukey]), 1)


                else:
                    PrintMsg("\t" + Number_Format(iComp, 0, True) + " components for "  + str(td) + " - " + str(bd) + "cm", 1)

                # Write out map unit aggregated AWS
                #
                for murec in muCursor:
                    mukey = murec[0]

                    if mukey in dMu:
                        compPct, hzT, aws = dMu[mukey]
                        murec[1] = compPct
                        murec[2] = aws
                        murec[3] = round(hzT, 2)  # sometimes this ends up being 2 or 3X what it should
                        muCursor.updateRow(murec)

        if len(missingList) > 0:
            missingList = list(set(missingList))
            PrintMsg(" \n\tFollowing mapunits have no comppct_r: " + ", ".join(missingList), 1)

        PrintMsg("", 0)

        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CalcSOC(inputDB, outputDB, theCompTable, theMuTable, dPct, dFrags, depthList, dRestrictions, maxD):
    # Modified SDP 2017-10-12
    #
    # Create a component-level summary table
    # Calculate the standard mapunit-weighted available SOC for each mapunit and
    # add it to the map unit-level table
    # Does not calculate SOC below the following component restrictions:
    #     Lithic bedrock, Paralithic bedrock, Densic bedrock, Fragipan, Duripan, Sulfuric

    try:
        # Using the same component horizon table that has been
        queryTbl = os.path.join(outputDB, "QueryTable_HZ")
        numRows = int(arcpy.GetCount_management(queryTbl).getOutput(0))

        # mukey, cokey, compPct,val, top, bot
        #qFieldNames = ["mukey", "cokey", "comppct_r", "hzdept_r", "hzdepb_r", "om_r", "dbthirdbar_r"]

        qFieldNames = ["mukey","cokey","comppct_r","compname","localphase","chkey","om_r","dbthirdbar_r", "hzdept_r","hzdepb_r"]

        # Track map units that are missing data
        missingList = list()
        minusList = list()

        bCarbon = False # Temporary flag. Dump out SOC 0-30 data to a csv file

        PrintMsg(" \n\tCalculating soil organic carbon for:", 0)

        for rng in depthList:
            # Calculating and updating just one SOC column at a time
            #
            td = rng[0]
            bd = rng[1]

            # Open output table Mu...All in write mode
            # I lately added the "MUSUMCPCTS" to the output. Need to check output because
            # it will be writing this out for every range. Lots more overhead.
            #

            # Create dictionaries to handle the mapunit and component summaries
            dMu = dict()
            dComp = dict()
            #dSumPct = dict()  # store the sum of comppct_r for each mapunit to use in the calculations
            dSum = dict()     # store sum of comppct_r and total thickness for the component
            dHz = dict()      # Trying a new dictionary that will s
            mCnt = 0
            dMinMax = dict()

            arcpy.SetProgressorLabel("Creating output tables using dominant component...")
            arcpy.SetProgressor("step", "Aggregating data for the dominant component..." , 0, numRows, 1)

            # Open edit session on geodatabase to allow multiple insert cursors
            with arcpy.da.Editor(inputDB) as edit:

                # Open output mapunit-level table in update mode
                muFieldNames = ["MUKEY", "MUSUMCPCTS", "SOC" + str(td) + "_" + str(bd), "TK" + str(td) + "_" + str(bd) + "S"]
                muCursor = arcpy.da.UpdateCursor(theMuTable, muFieldNames)

                # Open output component-level table in write mode

                coFieldNames = ["COKEY", "SOC" + str(td) + "_" + str(bd), "TK" + str(td) + "_" + str(bd) + "S"]
                coCursor = arcpy.da.UpdateCursor(theCompTable, coFieldNames)

                # Process query table using a searchcursor, write out horizon data for each component
                # At this time, almost all components are being used! There is no filter.
                hzSQL = "hzdept_r is not null"  # prevent divide-by-zero errors by skipping components with no horizons
                sqlClause = (None, "order by mukey, comppct_r DESC, cokey, hzdept_r ASC")

                iCnt = int(arcpy.GetCount_management(queryTbl).getOutput(0))
                inCur = arcpy.da.SearchCursor(queryTbl, qFieldNames, where_clause=hzSQL, sql_clause=sqlClause)
                arcpy.SetProgressor("step", "Reading QueryTable_HZ ...",  0, iCnt, 1)

                for rec in inCur:
                    # read each horizon-level input record from the query table ...

                    mukey, cokey, compPct, compName, localPhase, chkey, om, db3, top, bot = rec
                    sumCompPct = float(dPct[mukey][0])

                    if om is not None and db3 is not None:
                        # Calculate sum of horizon thickness and sum of component ratings for
                        # that portion of the horizon that is with in the td-bd range
                        top = max(top, td)
                        bot = min(bot, bd)
                        om = round(om, 3)

                        try:
                            rz, resKind = dRestrictions[cokey]

                        except:
                            rz = maxD
                            resKind = ""

                        # Now check for horizon restrictions within this range. Do not calculate SOC past
                        # root zone restrictive layers.
                        #
                        if top < rz < bot:
                            # restriction found in this horizon, use it to set a new depth
                            #PrintMsg("\t\t" + resKind + " restriction for " + mukey + ":" + cokey + " at " + str(rz) + "cm", 1)
                            cBot = rz

                        else:
                            cBot = min(rz, bot)

                        # Calculate initial usable horizon thickness
                        hzT = cBot - top

                        if hzT > 0 and top < cBot:
                            # get horizon fragment volume
                            try:
                                fragvol = dFrags[chkey]

                            except:
                                fragvol = 0.0
                                pass

                            # Calculate SOC using horizon thickness, OM, BD, FragVol, CompPct.
                            # changed the OM to carbon conversion from * 0.58 to / 1.724 after running FY2017 value table
                            db3 = round(db3, 2)

                            soc =  ( (hzT * ( ( om / 1.724 ) * db3 )) / 100.0 ) * ((100.0 - fragvol) / 100.0) * ( compPct * 100 )

                            #if td == 0 and bd == 5.0:
                                # Everything here matches the other script
                            #    test = [mukey, cokey, compPct, compName, localPhase, chkey, om, db3, top, bot, hzT, fragvol, round(soc, 2)]
                                #PrintMsg(str(test), 1)

                            if not cokey in dComp:
                                # Create initial entry for this component using the first horizon CHK
                                dComp[cokey] = (mukey, compPct, hzT, soc)

                            else:
                                # accumulate total thickness and total rating value by adding to existing component values  CHK
                                mukey, compName, dHzT, dSOC = dComp[cokey]
                                dSOC = dSOC + soc
                                dHzT = dHzT + hzT
                                dComp[cokey] = (mukey, compPct, dHzT, dSOC)

                    arcpy.SetProgressorPosition()

                # get the total number of major components from the dictionary count
                iComp = len(dComp)

                # Read through the component-level data and summarize to the mapunit level
                #
                if iComp > 0:
                    PrintMsg("\t\t" + str(td) + " - " + str(bd) + "cm (" + Number_Format(iComp, 0, True) + " components)", 0)
                    arcpy.SetProgressor("step", "Saving map unit and component SOC data...",  0, iComp, 1)

                    for corec in coCursor:
                        # Could this be where I am losing minor components????
                        #
                        # get component level data  CHK
                        cokey = corec[0]

                        if cokey in dComp:
                            # get SOC-related data from dComp by cokey
                            # reminder that soc = ( (hzT * ( ( om * 0.58 ) * db3 )) / 100.0 ) * ((100.0 - fragvol) / 100.0) * ( compPct * 100 )
                            mukey, compPct, hzT, soc = dComp[corec[0]]

                            # get sum of component percent for the mapunit (all components???)
                            # Value[0] is for all components,
                            # Value[1] is just for major-earthy components,
                            # Value[2] is all major components
                            # Value[3] is earthy components
                            try:
                                sumCompPct = float(dPct[mukey][0]) # Sum comppct for ALl components

                            except:
                                # set the component percent to zero if it is not found in the
                                # dictionary. This is probably a 'Miscellaneous area' not included in the  CHK
                                # data or it has no horizon information.
                                sumCompPct = 0.0


                            # calculate component percentage adjustment
                            if sumCompPct > 0:

                                # write the new component-level SOC data to the Co_VALU table
                                #soc = soc  * 100.0 * compPct / sumCompPct   # metric tons per hectare for this component
                                #soc = soc  * 10000 * compPct / sumCompPct    # grams per square meter for this component
                                # soc = soc * compPct / sumCompPct    # grams per square meter for this component  2017-11-14
                                corec[1] = soc                      # Test
                                hzT = hzT * compPct / 100.0         # Adjust component share of horizon thickness by comppct/100
                                #hzT = hzT * compPct / adjCompPct   # Adjust component share of horizon thickness by (comppct/sum of comppct)
                                corec[2] = hzT                      # This is new for the TK0_5A column
                                coCursor.updateRow(corec)

                                # Update component values in component dictionary   CHK
                                dComp[cokey] = mukey, compPct, hzT, soc

                                if mukey in dMu:
                                    # add this component's data to the map unit
                                    val1, val2, val3 = dMu[mukey]
                                    compPct = compPct + val1
                                    hzT = hzT + val2
                                    soc = soc + val3

                                dMu[mukey] = (compPct, hzT, soc)
                                #PrintMsg(str((compPct, hzT, soc)), 1)

                        arcpy.SetProgressorPosition()

                    arcpy.ResetProgressor()

                else:
                    PrintMsg("\t" + Number_Format(iComp, 0, True) + " components for "  + str(td) + " - " + str(bd) + "cm", 1)

                # Write out map unit aggregated SOC
                #
                for murec in muCursor:
                    mukey = murec[0]

                    if mukey in dMu:
                        compPct, hzT, soc = dMu[mukey]
                        murec[1] = compPct
                        murec[2] = round(soc, 0)
                        murec[3] = round(hzT, 0)  # this value appears to be low sometimes
                        muCursor.updateRow(murec)

                        #if td == 0 and bd == 100.0:
                            # Mismatch here for some mapunits
                        #    PrintMsg(str(murec), 1)


        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def GetFragVol(inputDB):
    # Get the horizon summary of rock fragment volume (percent)
    # load sum of comppct_r into a dictionary by chkey. This
    # value will be used to reduce amount of SOC for each horizon
    # If not all horizons are not present in the dictionary, failover to
    # zero for the fragvol value.

    try:

        fragFlds = ["chkey", "fragvol_r"]

        dFrags = dict()

        with arcpy.da.SearchCursor(os.path.join(inputDB, "chfrags"), fragFlds) as fragCur:
            for rec in fragCur:
                chkey, fragvol = rec

                if chkey in dFrags:
                    # This horizon already has a volume for another fragsize
                    # Get the existing value and add to it.
                    # limit total fragvol to 100 or we will get negative SOC values where there
                    # are problems with fragvol data
                    val = dFrags[chkey]
                    dFrags[chkey] = min(val + max(fragvol, 0), 100)

                else:
                    # this is the first component for this map unit
                    dFrags[chkey] = min(max(fragvol, 0), 100)

        # in the rare case where fragvol sum is greater than 100%, return 100
        return dFrags

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return dict()

    except:
        errorMsg()
        return dict()


## ===================================================================================
def GetSumPct(inputDB):
    # Get map unit - sum of component percent for all components and also for major-earthy components
    # load sum of comppct_r into a dictionary.
    # Value[0] is for all components,
    # Value[1] is just for major-earthy components,
    # Value[2] is all major components
    # Value[3] is earthy components
    #
    # Do I need to add another option for earthy components?
    # WSS and SDV use all components with data for AWS.

    try:
        pctSQL = "comppct_r is not null"
        pctFlds = ["mukey", "compkind", "majcompflag", "comppct_r"]

        dPct = dict()

        with arcpy.da.SearchCursor(os.path.join(inputDB, "component"), pctFlds, pctSQL) as pctCur:
            for rec in pctCur:
                mukey, compkind, flag, comppct = rec
                m = 0     # major component percent
                me = 0    # major-earthy component percent
                e = 0     # earthy component percent

                if flag == 'Yes':
                    # major component percent
                    m = comppct

                    if not compkind in  ["Miscellaneous area", ""]:
                        # major-earthy component percent
                        me = comppct
                        e = comppct

                    else:
                        me = 0

                elif not compkind in  ["Miscellaneous area", ""]:
                    e = comppct

                if mukey in dPct:
                    # This mapunit has a pair of values already
                    # Get the existing values from the dictionary
                    #pctAll, pctMjr = dPct[mukey] # all components, major-earthy
                    pctAll, pctME, pctMjr, pctE = dPct[mukey]
                    dPct[mukey] = (pctAll + comppct, pctME + me, pctMjr + m, pctE + e)

                else:
                    # this is the first component for this map unit
                    dPct[mukey] = (comppct, me, m, e)

        return dPct

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return dict()

    except:
        errorMsg()
        return dict()

## ===================================================================================
def MakeNCCPIQueryTable(inputDB, qTable):
    # create query table containing information from component and chorizon tables
    # return name of querytable. Failure returns an empty string for the table name.
    #
    # Bob Dobos wanted the Valu1 table to use only major components for NCCPI
    #
    # Web Soil Survey uses ALL components, not just majors. To switch to the WSS method,
    # remove the filter for major component. May need to filter out null comppct_r.
    #
    # COINTERP.RULENAME CHOICES FOR NCCPI Version 2:
    #
    # 'NCCPI - National Commodity Crop Productivity Index (Ver 2.0)'
    # 'NCCPI - NCCPI Corn and Soybeans Submodel (II)'
    # 'NCCPI - NCCPI Cotton Submodel (II)'
    # 'NCCPI - NCCPI Small Grains Submodel (II)'
    #
    #
    # FY2018 Big change. NCCPI version 3 will be available. Main rulename will change.
    # Soybeans will be split out from 'Corn and Soybeans', requiring a new column in the
    # Valu1 table.
    #
    # NCCPI version 3 Information
    # -------------------------------------
    # MRULENAME:	NCCPI - National Commodity Crop Productivity Index (Ver 3.0)  (ruledepth=0)
    #
    # RULENAME:	NCCPI - NCCPI Cotton Submodel (II)		(ruledepth=1)
    # RULENAME:	NCCPI - NCCPI Small Grains Submodel (II)	(ruledepth=1)
    # RULENAME:	NCCPI - NCCPI Corn Submodel (I)			(ruledepth=1)
    # RULENAME:	NCCPI - NCCPI Soybeans Submodel (I)		(ruledepth=1)

    try:

        # Join chorizon table with component table
        inTables = [os.path.join(inputDB, "component"), os.path.join(inputDB, "cointerp")]

        # interphr is the fuzzy value
        theFields = [["COMPONENT.MUKEY", "MUKEY"], \
        ["COMPONENT.COKEY", "COKEY"], \
        ["COMPONENT.COMPPCT_R", "COMPPCT_R"], \
        ["COINTERP.RULENAME", "RULENAME"], \
        ["COINTERP.RULEDEPTH", "RULEDEPTH"], \
        ["COINTERP.INTERPHR", "INTERPHR"]]

        #theSQL = "COMPONENT.COMPPCT_R > 0 AND COMPONENT.MAJCOMPFLAG = 'Yes' AND COMPONENT.COKEY = COINTERP.COKEY  AND COINTERP.MRULENAME = '" + rule + "'"
        if bRulekey:
            # Much better performance if COINTER.RULEKEY is indexed and can be used in the query
            if mainRuleName == 'NCCPI - National Commodity Crop Productivity Index (Ver 2.0)':
                theSQL = "COMPONENT.MAJCOMPFLAG = 'Yes' AND COMPONENT.COKEY = COINTERP.COKEY  AND COINTERP.MRULEKEY = '34170'"

            else:
                theSQL = "COMPONENT.MAJCOMPFLAG = 'Yes' AND COMPONENT.COKEY = COINTERP.COKEY  AND COINTERP.MRULEKEY = '54955'"

        else:
            theSQL = "COMPONENT.MAJCOMPFLAG = 'Yes' AND COMPONENT.COKEY = COINTERP.COKEY  AND COINTERP.MRULENAME = '" + mainRuleName + "'"

        PrintMsg(" \n\tCalculating NCCPI weighted averages for all major components...", 0)
        #PrintMsg("Using SQL: " + theSQL, 1)

        # Things to be aware of with MakeQueryTable:
        # USE_KEY_FIELDS does not create OBJECTID field. Lack of OBJECTID precludes sorting on Mukey.
        # ADD_VIRTUAL_KEY_FIELD creates OBJECTID, but qualifies field names using underscore (eg. COMPONENT_COKEY)
        #
        arcpy.MakeQueryTable_management(inTables, qTable, "ADD_VIRTUAL_KEY_FIELD","",theFields, theSQL)

        if arcpy.Exists(qTable):
            iCnt = int(arcpy.GetCount_management(qTable).getOutput(0))
            if iCnt == 0:
                PrintMsg("\tFailed to retrieve NCCPI data", 1)
                return False

        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CalcNCCPI2(inputDB, theMuTable, qTable, dPct):
    #
    #
    try:
        # FY2018 Big change. NCCPI version 3 will be available. Main rulename will change.
        # Soybeans will be split out from 'Corn and Soybeans', requiring a new column in the
        # Valu1 table.
        #
        # NCCPI version 3 Information
        # -------------------------------------
        # MRULENAME:	NCCPI - National Commodity Crop Productivity Index (Ver 3.0)  (ruledepth=0)
        #
        # RULENAME:	NCCPI - NCCPI Cotton Submodel (II)		(ruledepth=1)
        # RULENAME:	NCCPI - NCCPI Small Grains Submodel (II)	(ruledepth=1)
        # RULENAME:	NCCPI - NCCPI Corn Submodel (I)			(ruledepth=1)
        # RULENAME:	NCCPI - NCCPI Soybeans Submodel (I)		(ruledepth=1)

        # and write to Mu_NCCPI2 table


        #
        #PrintMsg(" \n\tAggregating data to mapunit level...", 0)

        # Alternate component fields for all NCCPI values
        cFlds = ["MUKEY","COKEY","COMPPCT_R","COMPNAME","LOCALPHASE", "DUMMY"]
        mFlds = ["MUKEY","COMPPCT_R","COMPNAME","LOCALPHASE", "DUMMY"]

        # Create dictionary key as MUKEY:INTERPHRC
        # Need to look through the component rating class for ruledepth = 0
        # and sum up COMPPCT_R for each key value
        #
        dVals = dict()  # dictionary containing sum of comppct for each MUKEY:RATING combination

        # Get sum of component percent for each map unit. There are different options:
        #     1. Use all major components
        #     2. Use all components that have an NCCPI rating
        #     3. Use all major-earthy components. This one is not currently available.
        #     4. Use all components (that have a component percent)
        #

        # Query table fields
        qFields = ["COMPONENT_MUKEY", "COMPONENT_COKEY", "COMPONENT_COMPPCT_R", "COINTERP_RULEDEPTH", "COINTERP_RULENAME", "COINTERP_INTERPHR"]

        sortFields = "ORDER BY COMPONENT_COKEY ASC, COMPONENT_COMPPCT_R DESC"
        querytblSQL = "COMPONENT_COMPPCT_R IS NOT NULL"  # all major components were set in the original query table
        sqlClause = (None, sortFields)

        iCnt = int(arcpy.GetCount_management(qTable).getOutput(0))
        noVal = list()  # Get a list of components with no overall index rating

        #PrintMsg(" \n\tReading query table with " + Number_Format(iCnt, 0, True) + " records...", 0)

        arcpy.SetProgressor("step", "Reading NCCPI query table...", 0,iCnt, 1)

        with arcpy.da.SearchCursor(qTable, qFields, where_clause=querytblSQL, sql_clause=sqlClause) as qCursor:

            for qRec in qCursor:
                # qFields = MUKEY, COKEY, COMPPCT_R, RULEDEPTH, RULENAME, INTERPHR
                mukey, cokey, comppct, ruleDepth, ruleName, fuzzyValue = qRec

                # Dictionary order:  All, CS, CT, SG
                if not mukey in dVals:
                    # Initialize mukey NCCPI values
                    dVals[mukey] = [None, None, None, None]

                if not fuzzyValue is None:

                    if ruleDepth == 0:
                        # This is NCCPI Overall Index
                        oldVal = dVals[mukey][0]

                        if oldVal is None:
                            dVals[mukey][0] = fuzzyValue * comppct

                        else:
                            dVals[mukey][0] = (oldVal + (fuzzyValue * comppct))

                    # The rest of these will be ruledepth=1
                    #
                    elif ruleName == "NCCPI - NCCPI Corn and Soybeans Submodel (II)":
                        oldVal = dVals[mukey][1]

                        if oldVal is None:
                            dVals[mukey][1] = fuzzyValue * comppct

                        else:
                            dVals[mukey][1] = (oldVal + (fuzzyValue * comppct))

                    elif ruleName == "NCCPI - NCCPI Cotton Submodel (II)":
                        oldVal = dVals[mukey][2]

                        if oldVal is None:
                            dVals[mukey][2] =  fuzzyValue * comppct

                        else:
                            dVals[mukey][2] = (oldVal + (fuzzyValue * comppct))

                    elif ruleName == "NCCPI - NCCPI Small Grains Submodel (II)":
                        oldVal = dVals[mukey][3]

                        if oldVal is None:
                            dVals[mukey][3] = fuzzyValue * comppct

                        else:
                            dVals[mukey][3] = (oldVal + (fuzzyValue * comppct))

                elif ruleName == "NCCPI - National Commodity Crop Productivity Index (Ver 2.0)":
                    # This component does not have an NCCPI rating
                    #PrintMsg(" \n" + mukey + ":" + cokey + ", " + str(comppct) + "% has no NCCPI rating", 1)
                    noVal.append("'" + cokey + "'")

                arcpy.SetProgressorPosition()
                #
                # End of query table iteration
                #



        #if len(noVal) > 0:
        #    PrintMsg(" \nThe following components had no NCCPI overall index: " + ", ".join(noVal), 1)

        iCnt = len(dVals)

        if iCnt > 0:

            #PrintMsg(" \n\tSaving map unit weighted NCCPI data (" + Number_Format(iCnt, 0, True) + " records) to " + os.path.basename(theMuTable) + "..." , 0)
            # Write map unit aggregate data to Mu_NCCPI2 table
            #
            # theMuTable is a global variable. Need to check this out in the gSSURGO_ValuTable script

            with arcpy.da.UpdateCursor(theMuTable, ["mukey", "NCCPI2CS", "NCCPI2CO","NCCPI2SG", "NCCPI2ALL"]) as muCur:

                arcpy.SetProgressor("step", "Saving map unit weighted NCCPI data to VALU table...", 0, iCnt, 0)
                for rec in muCur:
                    mukey = rec[0]

                    try:
                        # Get output values from dVals and dPct dictionaries
                        #val = dVals[mukey]
                        ovrall, cs, co, sg = dVals[mukey]
                        sumPct = dPct[mukey][2]  # sum of major-earthy components
                        if not cs is None:
                            cs = round(cs / sumPct, 3)

                        if not co is None:
                            co = round(co / sumPct, 3)

                        if not sg is None:
                            sg = round(sg / sumPct, 3)

                        if not ovrall is None:
                            ovrall = round(ovrall / sumPct, 3)

                        newrec = mukey, cs, co, sg, ovrall
                        muCur.updateRow(newrec)

                    except:
                        # Miscellaneous map unit encountered with no comppct_r?
                        pass

                    arcpy.SetProgressorPosition()

            arcpy.Delete_management(qTable)
            return True

        else:
            raise MyError, "No NCCPI data processed"

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False


## ===================================================================================
def CalcNCCPI3(inputDB, theMuTable, qTable, dPct):
    #
    #
    try:
        # FY2018 Big change. NCCPI version 3 will be available. Main rulename will change.
        # Soybeans will be split out from 'Corn and Soybeans', requiring a new column in the
        # Valu1 table.
        #
        # NCCPI version 3 Information
        # -------------------------------------
        # MRULENAME:	NCCPI - National Commodity Crop Productivity Index (Ver 3.0)  (ruledepth=0)
        #
        # RULENAME:	NCCPI - NCCPI Cotton Submodel (II)		(ruledepth=1)
        # RULENAME:	NCCPI - NCCPI Small Grains Submodel (II)	(ruledepth=1)
        # RULENAME:	NCCPI - NCCPI Corn Submodel (I)			(ruledepth=1)
        # RULENAME:	NCCPI - NCCPI Soybeans Submodel (I)		(ruledepth=1)

        # and write to Mu_NCCPI2 table

        #
        #PrintMsg(" \n\tAggregating data to mapunit level...", 0)

        # Alternate component fields for all NCCPI values
        cFlds = ["MUKEY","COKEY","COMPPCT_R","COMPNAME","LOCALPHASE", "DUMMY"]
        mFlds = ["MUKEY","COMPPCT_R","COMPNAME","LOCALPHASE", "DUMMY"]

        # Create dictionary key as MUKEY:INTERPHRC
        # Need to look through the component rating class for ruledepth = 0
        # and sum up COMPPCT_R for each key value
        #
        dVals = dict()  # dictionary containing sum of comppct for each MUKEY:RATING combination

        # Get sum of component percent for each map unit. There are different options:
        #     1. Use all major components
        #     2. Use all components that have an NCCPI rating
        #     3. Use all major-earthy components. This one is not currently available.
        #     4. Use all components (that have a component percent)
        #

        # Query table fields
        qFields = ["COMPONENT_MUKEY", "COMPONENT_COKEY", "COMPONENT_COMPPCT_R", "COINTERP_RULEDEPTH", "COINTERP_RULENAME", "COINTERP_INTERPHR"]

        sortFields = "ORDER BY COMPONENT_COKEY ASC, COMPONENT_COMPPCT_R DESC"
        querytblSQL = "COMPONENT_COMPPCT_R IS NOT NULL"  # all major components were set in the original query table
        sqlClause = (None, sortFields)

        iCnt = int(arcpy.GetCount_management(qTable).getOutput(0))
        noVal = list()  # Get a list of components with no overall index rating

        PrintMsg(" \n\tReading query table with " + Number_Format(iCnt, 0, True) + " records...", 0)

        arcpy.SetProgressor("step", "Reading NCCPI query table...", 0, iCnt, 1)

        with arcpy.da.SearchCursor(qTable, qFields, where_clause=querytblSQL, sql_clause=sqlClause) as qCursor:

            for qRec in qCursor:
                # qFields = MUKEY, COKEY, COMPPCT_R, RULEDEPTH, RULENAME, INTERPHR
                mukey, cokey, comppct, ruleDepth, ruleName, fuzzyValue = qRec

                # Dictionary order:  All, CT, CR, SB, SG
                if not mukey in dVals:
                    # Initialize mukey NCCPI values
                    dVals[mukey] = [None, None, None, None, None]

                if not fuzzyValue is None:

                    if ruleDepth == 0:
                        # This is NCCPI Overall Index
                        oldVal = dVals[mukey][0]

                        if oldVal is None:
                            dVals[mukey][0] = fuzzyValue * comppct

                        else:
                            dVals[mukey][0] = (oldVal + (fuzzyValue * comppct))

                    # The rest of these will be ruledepth=1
                    #
                    elif ruleName == "NCCPI - NCCPI Cotton Submodel (II)":
                        oldVal = dVals[mukey][1]

                        if oldVal is None:
                            dVals[mukey][1] =  fuzzyValue * comppct

                        else:
                            dVals[mukey][1] = (oldVal + (fuzzyValue * comppct))

                    elif ruleName == "NCCPI - NCCPI Corn Submodel (I)":
                        oldVal = dVals[mukey][2]

                        if oldVal is None:
                            dVals[mukey][2] = fuzzyValue * comppct

                        else:
                            dVals[mukey][2] = (oldVal + (fuzzyValue * comppct))

                    elif ruleName == "NCCPI - NCCPI Soybeans Submodel (I)":
                        oldVal = dVals[mukey][3]

                        if oldVal is None:
                            dVals[mukey][3] = fuzzyValue * comppct

                        else:
                            dVals[mukey][3] = (oldVal + (fuzzyValue * comppct))


                    elif ruleName == "NCCPI - NCCPI Small Grains Submodel (II)":
                        oldVal = dVals[mukey][4]

                        if oldVal is None:
                            dVals[mukey][4] = fuzzyValue * comppct

                        else:
                            dVals[mukey][4] = (oldVal + (fuzzyValue * comppct))

                    #elif ruleName.startswith("NCCPI"):
                    #    PrintMsg(" \n" + mukey + ":" + cokey + ", " + str(ruleName), 1)

                    #else:
                        # These would be rating reasons or impacted soils
                    #    PrintMsg(" \n" + mukey + ":" + cokey + ", " + str(ruleName), 1)


                elif ruleName.startswith("NCCPI - National Commodity Crop Productivity Index"):
                    # This component does not have an NCCPI rating
                    #PrintMsg(" \n" + mukey + ":" + cokey + ", " + str(comppct) + "% has no NCCPI rating", 1)
                    noVal.append("'" + cokey + "'")

                arcpy.SetProgressorPosition()
                #
                # End of query table iteration
                #



        #if len(noVal) > 0:
        #    PrintMsg(" \nThe following components had no NCCPI overall index: " + ", ".join(noVal), 1)

        iCnt = len(dVals)

        if iCnt > 0:

            #PrintMsg(" \n\tSaving map unit weighted NCCPI data (" + Number_Format(iCnt, 0, True) + " records) to " + os.path.basename(theMuTable) + "..." , 0)
            # Write map unit aggregate data to Mu_NCCPI2 table
            #
            # theMuTable is a global variable. Need to check this out in the gSSURGO_ValuTable script
            #                                                 corn&soybeans, cotton, smallgrains, overall

            with arcpy.da.UpdateCursor(theMuTable, ["mukey", "NCCPI3CORN", "NCCPI3SOY", "NCCPI3COT","NCCPI3SG", "NCCPI3ALL"]) as muCur:

                arcpy.SetProgressor("step", "Saving map unit weighted NCCPI data to VALU table...", 0, iCnt, 0)
                for rec in muCur:
                    mukey = rec[0]

                    try:
                        # Get output values from dVals and dPct dictionaries
                        #val = dVals[mukey]
                        ovrall, cot, corn, soy, sg = dVals[mukey]
                        sumPct = dPct[mukey][2]  # sum of major-earthy components

                        if not ovrall is None:
                            ovrall = round(ovrall / sumPct, 3)

                        if not cot is None:
                            cot = round(cot / sumPct, 3)

                        if not corn is None:
                            corn = round(corn / sumPct, 3)

                        if not soy is None:
                            soy = round(soy / sumPct, 3)

                        if not sg is None:
                            sg = round(sg / sumPct, 3)



                        # "mukey", "NCCPI2CORN", "NCCPI2SOY", "NCCPI2COT","NCCPI2SG", "NCCPI2ALL"
                        newrec = mukey, corn, soy, cot, sg, ovrall
                        muCur.updateRow(newrec)

                    except:
                        # Miscellaneous map unit encountered with no comppct_r?
                        pass

                    arcpy.SetProgressorPosition()

            arcpy.Delete_management(qTable)
            return True

        else:
            raise MyError, "No NCCPI data processed"

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CalcPWSL(inputDB, outputDB, theMuTable, dPct):
    # Get potential wet soil landscape rating for each map unit
    # Assuming that all components (with comppct_r) will be processed
    #
    # Sharon: I treat all map unit components the same, so if I find 1% water I think
    # it should show up as 1% PWSL.  If the percentage of water is >= 80% then I class
    # it into the water body category or 999.
    try:
        env.workspace = outputDB

        # Using the same component horizon table as always
        queryTbl = os.path.join(outputDB, "QueryTable_Hz")
        numRows = int(arcpy.GetCount_management(queryTbl).getOutput(0))
        PrintMsg(" \n\tCalculating Potential Wet Soil Landscapes using...", 0)
        qFieldNames = ["mukey", "muname", "cokey", "comppct_r",  "compname", "localphase", "otherph", "majcompflag", "compkind", "hydricrating", "drainagecl"]
        pwSQL = "COMPPCT_R > 0"
        compList = list()
        dMu = dict()

        drainList = ["Poorly drained", "Very poorly drained"]
        phaseList = ["drained", "undrained", "channeled", "protected", "ponded", "flooded"]

        # Defining water components SDP
        # 1. compkind = 'Miscellaneous area' or is NULL and (
        # 2. compname = 'Water' or
        # 3. compname like '% water' or
        # 4. compname like '% Ocean' or
        # 5. compname like '% swamp'
        # nameList = []

        iCnt = int(arcpy.GetCount_management(queryTbl).getOutput(0))
        lastCokey = 'xxx'
        arcpy.SetProgressor("step", "Reading query table table for wetland information...",  0, iCnt, 1)

        with arcpy.da.SearchCursor(queryTbl, qFieldNames, where_clause=pwSQL) as pwCur:
            for rec in pwCur:
                mukey, muname, cokey, comppct_r,  compname, localphase, otherph, majcompflag, compkind, hydricrating, drainagecl = rec

                if cokey != lastCokey:
                    # only process first horizon record for each component

                    compList.append(cokey)
                    # Only check the first horizon record, really only need component level
                    # Not very efficient, should problably create a new query table
                    #
                    # Need to split up these tests so that None types can be handled

                    # Sharon says that if the hydricrating for a component is 'No', don't
                    # look at it any further. If it is unranked, go ahead and look at
                    # other properties.
                    #
                    pw = False

                    if ( muname == "Water" or str(compname) == "Water" or (str(compname).lower().find(" water") >= 0) or (str(compname).lower().find(" ocean") >= 0)  or (str(compname).find(" swamp") >= 0) or str(compname) == "Swamp" ) :

                        # Check for water before looking at Hydric rating
                        # Probably won't catch everything. Waiting for Sharon's criteria.

                        if comppct_r >= 80:
                            # Flag this mapunit with a '999'
                            # Not necessarily catching map unit with more than one Water component that
                            # might sum to >= 80. Don't think there are any right now.
                            #PrintMsg("\tFlagging " + muname + " as Water", 1)
                            #PrintMsg("\t" + mukey + "; " + muname + "; " + compname + "; " + str(compkind) + "; " + str(comppct_r), 1)
                            pw = False
                            dMu[mukey] = 999

                        else:
                            pw = True

                            try:
                                sumPct = dMu[mukey]

                                if sumPct != 999:
                                    dMu[mukey] = sumPct + comppct_r

                            except:
                                dMu[mukey] = comppct_r

                    elif hydricrating == 'No':
                        # Added this bit so that other properties cannot override hydricrating = 'No'
                        pw = False

                    elif hydricrating == 'Yes':
                        # This is always a Hydric component
                        # Get component percent and add to map unit total PWSL
                        pw = True
                        #if mukey == tmukey:
                        #    PrintMsg("\tHydric percent = " + str(comppct_r), 1)

                        try:
                            sumPct = dMu[mukey]

                            if sumPct != 999:
                                dMu[mukey] = sumPct + comppct_r

                        except:
                            dMu[mukey] = comppct_r

                    elif hydricrating == 'Unranked':
                        # Not sure how Sharon is handling NULL hydric
                        #
                        # Unranked hydric from here on down, looking at other properties such as:
                        #   Local phase
                        #   Other phase
                        #   Drainage class
                        #   Map unit name strings
                        #       drainList = ["Poorly drained", "Very poorly drained"]
                        #       phaseList = ["drained", "undrained", "channeled", "protected", "ponded", "flooded"]

                        if [d for d in phaseList if str(localphase).lower().find(d) >= 0]:
                            pw = True

                            try:
                                sumPct = dMu[mukey]
                                dMu[mukey] = sumPct + comppct_r

                            except:
                                dMu[mukey] = comppct_r

                        # otherphase
                        elif [d for d in phaseList if str(otherph).lower().find(d) >= 0]:
                            pw = True

                            try:
                                sumPct = dMu[mukey]
                                dMu[mukey] = sumPct + comppct_r

                            except:
                                dMu[mukey] = comppct_r

                        # look for specific strings in the map unit name
                        elif [d for d in phaseList if muname.find(d) >= 0]:
                            pw = True
                            #if mukey == tmukey:
                            #    PrintMsg("\tMuname = " + muname, 1)

                            try:
                                sumPct = dMu[mukey]
                                dMu[mukey] = sumPct + comppct_r

                            except:
                                dMu[mukey] = comppct_r

                        elif str(drainagecl) in drainList:
                            pw = True

                            try:
                                sumPct = dMu[mukey]
                                dMu[mukey] = sumPct + comppct_r

                            except:
                                dMu[mukey] = comppct_r

                lastCokey = cokey # use this to skip the rest of the horizons for this component
                arcpy.SetProgressorPosition()

        if len(dMu) > 0:
            arcpy.SetProgressor("step", "Populating " + os.path.basename(theMuTable) + "...",  0, len(dMu), 1)

            # Populate the PWSL1POMU column in the map unit level table
            muFlds = ["mukey", "pwsl1pomu"]
            with arcpy.da.UpdateCursor(theMuTable, muFlds) as muCur:
                for rec in muCur:
                    mukey = rec[0]
                    try:
                        rec[1] = dMu[mukey]
                        muCur.updateRow(rec)

                    except:
                        pass

                    arcpy.SetProgressorPosition()

        arcpy.ResetProgressor()
        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

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
def UpdateMetadata(outputWS, target, surveyInfo):
    # Update metadata for target object (VALU1 table)
    #
    try:

        # Clear process steps from the VALU1 table. Mostly AddField statements.
        #
        # NOTE: The geoprocessing metadata conversion tools to not work in the 64 bit background processing
        #
        """
        Any script or script tools you run while inside Desktop honors the background processing setting.
        If background processing is turned on, the scripts will execute in the 64-bit space.

        When you execute a stand-alone Python script outside the application, you need to ensure
        you're running against the 64-bit Python installation to make use of 64-bit geoprocessing.
        Double-clicking a Python file from Windows Explorer will launch the file using whatever
        association Windows has set for the .py file. Typically, this is the last version of Python installed,
        which should be 64 bit. If you want to be absolutely sure which version of Python you're
        running against (32 or 64), it is best to fully qualify the Python executable when running
        your script at command line. For example, the following command will ensure the script is
        run as 64 bit:
                      c:\Python27\ArcGISx6410.2\python.exe c:\gisData\scripts\intersect.py.

        """
        # Determine whether this script is running in 32 or 64 bit mode
        pythonVersion = sys.version

        if pythonVersion.find("32 bit") == -1:
            # Print a non-fatal warning to the user that the metadata will not be updated in 64 bit mode
            PrintMsg(" \nWarning! Unable to update metadata when running under 64-bit background-mode", 1)
            return False

        if not arcpy.Exists(target):
            target = os.path.join(outputWS, target)

        # Remove geoprocessing history
        remove_gp_history_xslt = os.path.join(os.path.dirname(sys.argv[0]), "remove geoprocessing history.xslt")
        out_xml = os.path.join(env.scratchFolder, "xxClean.xml")

        if not arcpy.Exists(remove_gp_history_xslt):
            raise MyError, "Missing file: " + remove_gp_history_xslt

        if arcpy.Exists(out_xml):
            arcpy.Delete_management(out_xml)

        # Using the stylesheet, write 'clean' metadata to out_xml file and then import back in
        # It appears that the metadata tools do not work within 64 bit background processing for 10.4.
        # The failure does not even generate an error message.
        try:
            arcpy.XSLTransform_conversion(target, remove_gp_history_xslt, out_xml, "")
            arcpy.MetadataImporter_conversion(out_xml, os.path.join(outputWS, target))

        except:
            PrintMsg(" \nFailed to clean up metadata", 0)

        # Set metadata translator file
        dInstall = arcpy.GetInstallInfo()
        installPath = dInstall["InstallDir"]
        prod = r"Metadata/Translator/ARCGIS2FGDC.xml"
        mdTranslator = os.path.join(installPath, prod)

        if not arcpy.Exists(mdTranslator):
            raise MyError, "Missing metadata translator: " + mdTranslator

        # Define input and output XML files
        #mdExport = os.path.join(env.scratchFolder, "xxExport.xml")  # initial metadata exported from current data data
        xmlPath = os.path.dirname(sys.argv[0])

        if mainRuleName == "NCCPI - National Commodity Crop Productivity Index (Ver 3.0)":
            mdExport = os.path.join(xmlPath, "gSSURGO_ValuTable2.xml")  # template metadata stored in ArcTool folder

        elif mainRuleName == "NCCPI - National Commodity Crop Productivity Index (Ver 2.0)":
            mdExport = os.path.join(xmlPath, "gSSURGO_ValuTable.xml")  # template metadata stored in ArcTool folder

        mdImport = os.path.join(env.scratchFolder, "xxImport.xml")  # the metadata xml that will provide the updated info

        # Cleanup XML files from previous runs
        if os.path.isfile(mdImport):
            os.remove(mdImport)

        # Start editing metadata using search and replace
        #
        stDict = StateNames()
        st = os.path.basename(outputWS)[8:-4]

        if st in stDict:
            # Get state name from the geodatabase name
            mdState = stDict[st]

        else:
            mdState = ""

        # Set date strings for metadata, based upon today's date
        #
        d = datetime.now()
        #today = d.strftime('%Y%m%d')

        # Alternative to using today's date. Use the last SAVEREST date
        today = GetLastDate(outputWS)

        # Set fiscal year according to the current month. If run during January thru September,
        # set it to the current calendar year. Otherwise set it to the next calendar year.
        #
##        if d.month > 9:
##            fy = "FY" + str(d.year + 1)
##
##        else:
##            fy = "FY" + str(d.year)

        # As of July 2020, switch gSSURGO version format to YYYYMM
        fy = d.strftime('%Y%m')

        # Convert XML from template metadata to tree format
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
                    child.text = os.path.basename(target).title()

                    if mdState != "":
                        child.text = child.text + " - " + mdState

                elif child.tag == "edition":
                    if child.text.find('xxFYxx') >= 0:
                        child.text = child.text.replace('xxFYxx', fy)
                    else:
                        PrintMsg(" \n\tEdition: " + child.text, 1)

                    if child.text.find('xxTODAYxx') >= 0:
                        child.text = child.text.replace('xxTODAYxx', today)

                elif child.tag == "serinfo":
                    for subchild in child.iter('issue'):
                        if subchild.text == "xxFYxx":
                            subchild.text = fy

                        if child.text.find('xxTODAYxx') >= 0:
                            child.text = child.text.replace('xxTODAYxx', today)


        # Update place keywords
        #PrintMsg("\tplace keywords", 0)
        ePlace = root.find('idinfo/keywords/theme')

        if ePlace is not None:
            for child in ePlace.iter('themekey'):
                if child.text == "xxSTATExx":
                    #PrintMsg("\tReplaced xxSTATExx with " + mdState)
                    child.text = mdState

                elif child.text == "xxSURVEYSxx":
                    #child.text = "The Survey List"
                    child.text = surveyInfo

        else:
            PrintMsg("\tsearchKeys not found", 1)

        idDescript = root.find('idinfo/descript')

        if not idDescript is None:
            for child in idDescript.iter('supplinf'):
                #id = child.text
                #PrintMsg("\tip: " + ip, 1)
                if child.text.find("xxTODAYxx") >= 0:
                    #PrintMsg("\t\tip", 1)
                    child.text = child.text.replace("xxTODAYxx", today)

                if child.text.find("xxFYxx") >= 0:
                    #PrintMsg("\t\tip", 1)
                    child.text = child.text.replace("xxFYxx", fy)

        if not idDescript is None:
            for child in idDescript.iter('purpose'):
                #ip = child.text
                #PrintMsg("\tip: " + ip, 1)
                if child.text.find("xxFYxx") >= 0:
                    #PrintMsg("\t\tip", 1)
                    child.text = child.text.replace("xxFYxx", fy)

                if child.text.find("xxTODAYxx") >= 0:
                    #PrintMsg("\t\tip", 1)
                    child.text = child.text.replace("xxTODAYxx", today)

        idAbstract = root.find('idinfo/descript/abstract')
        if not idAbstract is None:
            iab = idAbstract.text

            if iab.find("xxFYxx") >= 0:
                #PrintMsg("\t\tip", 1)
                idAbstract.text = iab.replace("xxFYxx", fy)
                #PrintMsg("\tAbstract", 0)

        # Use contraints
        #idConstr = root.find('idinfo/useconst')
        #if not idConstr is None:
        #    iac = idConstr.text
            #PrintMsg("\tip: " + ip, 1)
        #    if iac.find("xxFYxx") >= 0:
        #        idConstr.text = iac.replace("xxFYxx", fy)
        #        PrintMsg("\t\tUse Constraint: " + idConstr.text, 0)

        # Update credits
        eIdInfo = root.find('idinfo')

        if not eIdInfo is None:

            for child in eIdInfo.iter('datacred'):
                sCreds = child.text

                if sCreds.find("xxTODAYxx") >= 0:
                    #PrintMsg("\tdata credits1", 1)
                    sCreds = sCreds.replace("xxTODAYxx", today)

                if sCreds.find("xxFYxx") >= 0:
                    #PrintMsg("\tdata credits2", 1)
                    sCreds = sCreds.replace("xxFYxx", fy)

                child.text = sCreds
                #PrintMsg("\tCredits: " + sCreds, 1)

        #  create new xml file which will be imported, thereby updating the table's metadata
        tree.write(mdImport, encoding="utf-8", xml_declaration=None, default_namespace=None, method="xml")

        # import updated metadata to the geodatabase table
        arcpy.MetadataImporter_conversion(mdExport, target)
        arcpy.ImportMetadata_conversion(mdImport, "FROM_FGDC", target, "DISABLED")

        # delete the temporary xml metadata files
        if os.path.isfile(mdImport):
            os.remove(mdImport)

        #if os.path.isfile(mdExport):
        #    os.remove(mdExport)

        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CreateValuTable(inputDB):
    # Run all processes from here

## SSURGO_ValuTable.py
## -------------------------------------------------
##
## List of query tables used in calculating Valu1
## -----------------------------------------------
## 1. Valu1 = theMuTable (inputDB)
##
## 2. Co_VALU = theCompTable
##
## 3. CreateQueryTables: HzTexture, QueryTable_CR, QueryTable_HZ,
##
## 4. NCCPI_Table
##
## 5. mapunit, component, chorizon, chtexturegrp, chtexture, corestrictions
##

    try:
        arcpy.overwriteOutput = True

        # Set location for temporary tables
        #outputDB = "IN_MEMORY"
        outputDB = env.scratchGDB

        try:
            # Let's get the mainrulename from the SDVAttribute table
            #
            # query for sdvattribute.attributename like 'National Commodity Crop Productivity Index%'
            # return value for 'nasisrulename'
            # Need to give preference to version 3.0 if it is available.
            sdvTbl = os.path.join(inputDB, "sdvattribute")
            wc = "attributename like 'National Commodity Crop Productivity Index%'"
            global mainRuleName
            global bRulekey
            ruleNames = list()

            with arcpy.da.SearchCursor(sdvTbl, ["nasisrulename"], where_clause=wc) as cur:
                for rec in cur:

                    rule = rec[0].encode('ascii')

                    if not rule in ruleNames:
                        ruleNames.append(rule)

            #PrintMsg(" \nSet main rulename to: " + mainRuleName, 1)
            if len(ruleNames) == 0:
                raise MyError, "Failed to get NCCPI rulename"

            elif len(ruleNames) == 1:
                mainRuleName = ruleNames[0]

            elif "NCCPI - National Commodity Crop Productivity Index (Ver 3.0)" in ruleNames:
                mainRuleName = "NCCPI - National Commodity Crop Productivity Index (Ver 3.0)"

            else:
                mainRuleName = "NCCPI - National Commodity Crop Productivity Index (Ver 2.0)"

            indexList = [indx.name.upper() for indx in arcpy.ListIndexes(os.path.join(inputDB, "cointerp"))]

            if "INDX_COINTERPMRULEKEY" in indexList:
                bRulekey = True

            else:
                bRulekey = False


        except:
            # Shouldn't we just bail out here?
            errorMsg()
            mainRuleName = ""
            raise MyError, "Unable to identify NCCPI mainrule in " + inputDB

        #PrintMsg(" \nUsing " + mainRuleName, 1)

        # Name of mapunit level output table (global variable)
        theMuTable = os.path.join(inputDB, "Valu1")

        # Name of component level output table (global variable)
        theCompTable = os.path.join(inputDB, "Co_VALU")

        # Set output workspace to same as the input table
        #env.workspace = os.path.dirname(arcpy.Describe(queryTbl).catalogPath)
        env.workspace = inputDB

        # Save record of any issues to a text file
        logFile = os.path.basename(inputDB)[:-4] + "_Problems.txt"
        logFile = os.path.join(os.path.dirname(inputDB), logFile)

        # Get the mapunit - sum of component percent for calculations
        dPct = GetSumPct(inputDB)
        if len(dPct) == 0:
            raise MyError, ""

        # Create initial set of query tables used for RZAWS, AWS and SOC
        if CreateQueryTables(inputDB, outputDB, 150.0) == False:
            raise MyError, ""

        # Create permanent output tables for the map unit and component levels
        depthList = [(0,5), (5, 20), (20, 50), (50, 100), (100, 150), (150, 999), (0, 20), (0, 30), (0, 100), (0, 150), (0, 999)]

        if CreateOutputTableMu(theMuTable, depthList, dPct) == False:
            raise MyError, ""

        if CreateOutputTableCo(theCompTable, depthList) == False:
            raise MyError, ""

        # Store component restrictions for root growth in a dictionary
        resListAWS = "('Lithic bedrock','Paralithic bedrock','Densic bedrock', 'Densic material', 'Fragipan', 'Duripan', 'Sulfuric')"
        dRZRestrictions = GetCoRestrictions(outputDB, 150.0, resListAWS)

        # Find the top restriction for each component, both from the corestrictions table and the horizon properties
        dComp2 = CalcRZDepth(inputDB, outputDB, theCompTable, theMuTable, 150.0, dPct, dRZRestrictions)
        del dRZRestrictions

        # Calculate root zone available water capacity using a floor of 150cm or a root restriction depth
        #
        # dComp2[cokey] = [mukey, compName, localPhase, compPct, resDept, restriction]
        if CalcRZAWS(inputDB, outputDB, 0.0, 150.0, theCompTable, theMuTable, dComp2, 150.0, dPct) == False:
            raise MyError, ""

        # Calculate standard available water supply
        if CalcAWS(inputDB, outputDB, theCompTable, theMuTable, dPct, depthList) == False:
            raise MyError, ""

        # Run SOC calculations
        # Seems to be a problem with SOC calculations, numbers are high
        maxD = 999.0
        # Get bedrock restrictions for SOC  and write them to the output tables
        resListSOC = "('Lithic bedrock', 'Paralithic bedrock', 'Densic bedrock')"
        dSOCRestrictions = GetCoRestrictions(outputDB, maxD, resListSOC)

        # Store all component-horizon fragment volumes (percent) in a dictionary (by chkey)
        # and use in the root zone SOC calculations
        dFrags = GetFragVol(inputDB)

        if len(dFrags) == 0:
            raise MyError, "No fragment volume information"

        # Calculate soil organic carbon for all the different depth ranges
        depthList = [(0,5), (5, 20), (20, 50), (50, 100), (100, 150), (150, 999), (0, 20), (0, 30), (0, 100), (0, 150), (0, 999)]
        if CalcSOC(inputDB, outputDB, theCompTable, theMuTable, dPct, dFrags, depthList, dSOCRestrictions, maxD) == False:
            raise MyError, ""

        del dSOCRestrictions

        # Calculate NCCPI
        # Create query table using component and chorizon tables
        arcpy.SetProgressor("default", "Calculating NCCPI data elements...")
        nccpiTbl = "NCCPI_Table"

        if  MakeNCCPIQueryTable(inputDB, nccpiTbl) == False:
            pass

        else:
            if mainRuleName == "NCCPI - National Commodity Crop Productivity Index (Ver 3.0)":
                if CalcNCCPI3(inputDB, theMuTable, nccpiTbl, dPct) == False:
                    raise MyError, ""

            elif mainRuleName == "NCCPI - National Commodity Crop Productivity Index (Ver 2.0)":
                if CalcNCCPI2(inputDB, theMuTable, nccpiTbl, dPct) == False:
                    raise MyError, ""

        # Calculate Potential Wetland Soils
        #
        if CalcPWSL(inputDB, outputDB, theMuTable, dPct) == False:
            raise MyError, ""

        PrintMsg(" \n\tAll calculations complete", 0)

        # Create metadata for the VALU table
        # Query the output SACATALOG table to get list of surveys that were exported to the gSSURGO
        #
        saTbl = os.path.join(inputDB, "sacatalog")
        expList = list()
        queryList = list()

        with arcpy.da.SearchCursor(saTbl, ["AREASYMBOL", "SAVEREST"]) as srcCursor:
            for rec in srcCursor:
                expList.append(rec[0] + " (" + str(rec[1]).split()[0] + ")")
                queryList.append("'" + rec[0] + "'")

        surveyInfo = ", ".join(expList)
        queryInfo = ", ".join(queryList)

        # Update metadata for the geodatabase and all featureclasses
        PrintMsg(" \n\tUpdating " + os.path.basename(theMuTable) + " metadata...", 0)
        bMetadata = UpdateMetadata(inputDB, theMuTable, surveyInfo)

        if bMetadata:
            PrintMsg("\t\tMetadata complete", 0)

        else:
            PrintMsg("\t\tSkipping Valu1 table metadata...", 1)

        # Cleanup temporary tables...
        if arcpy.Exists(theCompTable):
            arcpy.Delete_management(theCompTable)

        if arcpy.Exists(os.path.join(env.scratchGDB, "QueryTable_CR")):
            arcpy.Delete_management(os.path.join(env.scratchGDB, "QueryTable_CR"))

        if arcpy.Exists(os.path.join(env.scratchGDB, "QueryTable_HZ")):
            arcpy.Delete_management(os.path.join(env.scratchGDB, "QueryTable_HZ"))

        PrintMsg(" \n\tValu1 table complete for " + inputDB + " \n ", 0)

        return True

    except MyError, e:
        # Example: raise MyError("this is an error message")
        PrintMsg(str(e) + " \n", 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
## ====================================== Main Body ==================================
# Import modules
import os, sys, string, re, locale, arcpy, traceback, collections
from operator import itemgetter, attrgetter
import xml.etree.cElementTree as ET
from datetime import datetime
from arcpy import env

# Original input table fields:
# areasymbol, mukey, musym, muname, muname, cokey, compct, compname, compkind, localphase,
# taxorder, taxsubgrp, ec, pH, dbthirdbar, hzname, hzdesgn, hzdept, hzdepb, hzthk, sand, silt,
# clay, om, reskind, reshard, resdept, resthk, texture, lieutex

# Compkind values for major components: Miscellaneous area, Series, Taxon above family,
# Family, Taxadjunct, Variant

# chtexturegrp.texture: 3,468 unique values, too many to list here. Bob's queries only
# look at excluding 'COP-MAT' texture from the Dense Layer calculation. He identifies the rest
# of the organic horizons using lieutext.

# lieutext values: Slightly decomposed plant material, Moderately decomposed plant material,
# Bedrock, Variable, Peat, Material, Unweathered bedrock, Sand and gravel, Mucky peat, Muck,
# Highly decomposed plant material, Weathered bedrock, Cemented, Gravel, Water, Cobbles,
# Stones, Channers, Parachanners, Indurated, Cinders, Duripan, Fragmental material, Paragravel,
# Artifacts, Boulders, Marl, Flagstones, Coprogenous earth, Ashy, Gypsiferous material,
# Petrocalcic, Paracobbles, Diatomaceous earth, Fine gypsum material, Undecomposed organic matter
#
# reskind values: Strongly contrasting textural stratification, Lithic bedrock, Densic material,
# Ortstein, Permafrost, Paralithic bedrock, Cemented horizon, Undefined, Fragipan, Plinthite,
# Abrupt textural change, Natric, Petrocalcic, Duripan, Densic bedrock, Salic,
# Human-manufactured materials, Sulfuric, Placic, Petroferric, Petrogypsic

# Dobos - NASIS lieutext matches: mpm, mpt, muck, peat, spm, udom, pdom, hpm
#
# Paul's organic horizon filters:  chtexturegrp.texture <> 'SPM', <>'UDOM'???, NOT LIKE: '%MPT%', '%MUCK', '%PEAT%' (from SVI query)
#
# Desgnmaster filter:  hzdesn IN ["O", "O'", "L"]
#
# Taxonomic Order filter:  upper(taxorder) LIKE 'HISTOSOLS'. Is this being used?
# Perhaps I should be using taxsubgrp.lower() like '%histic%' or use both!!!

#
# compkind filter for earthy components:  <> 'Miscellaneous area'


try:
    if __name__ == "__main__":

        # Create geoprocessor object
        #gp = arcgisscripting.create(9.3)

        inputDB = arcpy.GetParameterAsText(0)            # Input gSSURGO database

        bValu = CreateValuTable(inputDB)


except MyError, e:
    # Example: raise MyError("this is an error message")
    PrintMsg(str(e) + " \n", 2)

except:
    errorMsg()
