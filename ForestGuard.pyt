# ------------------------------------------------------------------------------
# Dead Trees Detection Toolbox (.pyt)
# Author: Liubov Dumarevskaya
# Email: luba.dm@gmail.com
# GitHub: https://github.com/LiubovD
# Last Modified: November 2025
#
# Description:
# This ArcGIS Pro Python Toolbox detects likely dead or declining trees from
# high-resolution aerial imagery. The workflow combines unsupervised raster
# classification, blue-band intensity filtering, morphological smoothing, and
# polygon conversion. Final tree features are cleaned using size thresholds,
# buffering, and dissolving to reduce noise and isolate individual dead-tree
# crowns or clusters.
#
# Key Features:
# • Accepts ANY raster layer from the project, or any raster file from disk.
# • Automatically normalizes raster layers to dataset format (fixes GP errors).
# • Optional forest mask to limit analysis to forested areas.
# • All intermediate files stored in a timestamped temporary folder next to GDB.
# • Optional automatic deletion of temporary folder after processing.
#
# License: MIT License
# ------------------------------------------------------------------------------

import arcpy
from pathlib import Path
from datetime import datetime
import shutil


# ==============================================================================
# Toolbox
# ==============================================================================

class Toolbox(object):
    def __init__(self):
        self.label = "Dead Trees Detection Toolbox"
        self.alias = "DeadTrees"
        self.tools = [DetectDeadTrees]


# ==============================================================================
# Tool
# ==============================================================================

class DetectDeadTrees(object):

    def __init__(self):
        self.label = "Detect Dead Trees"
        self.description = "Detects likely dead trees from aerial imagery."
        self.canRunInBackground = False

    # --------------------------------------------------------------------------
    # Parameters
    # --------------------------------------------------------------------------
    def getParameterInfo(self):
        params = []

        # INPUT RASTER — dropdown from project OR browse from disk
        # DO NOT add filters — important!
        p0 = arcpy.Parameter(
            displayName="Input Aerial Image (Layer or File)",
            name="input_raster",
            datatype="GPRasterLayer",
            parameterType="Required",
            direction="Input")
        params.append(p0)

        p1 = arcpy.Parameter(
            displayName="Forest Mask Layer (Optional)",
            name="mask_layer",
            datatype="GPFeatureLayer",
            parameterType="Optional",
            direction="Input")
        p1.filter.list = ["Polygon"]
        params.append(p1)

        p2 = arcpy.Parameter(
            displayName="Output Workspace (File Geodatabase)",
            name="workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")
        params.append(p2)

        p3 = arcpy.Parameter(
            displayName="Number of Classes (Iso Cluster)",
            name="number_classes",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        p3.value = 10
        params.append(p3)

        p4 = arcpy.Parameter(
            displayName="Minimum Tree Area (sq. meters)",
            name="min_area",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        p4.value = 2.0
        params.append(p4)

        p5 = arcpy.Parameter(
            displayName="Buffer Distance (meters)",
            name="buffer_distance",
            datatype="GPLinearUnit",
            parameterType="Optional",
            direction="Input")
        p5.value = "1 Meters"
        params.append(p5)

        p6 = arcpy.Parameter(
            displayName="Minimum Buffer Area (sq. meters)",
            name="min_buffer_area",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        p6.value = 30.0
        params.append(p6)

        p7 = arcpy.Parameter(
            displayName="Final Output Feature Class",
            name="output_features",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        params.append(p7)

        p8 = arcpy.Parameter(
            displayName="Blue Band Index (optional)",
            name="blue_band_index",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        p8.filter.type = "Range"
        p8.filter.list = [1, 15]
        params.append(p8)

        p9 = arcpy.Parameter(
            displayName="Enable Parallel Processing",
            name="enable_parallel",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        p9.value = True
        params.append(p9)

        p10 = arcpy.Parameter(
            displayName="Delete Temporary Folder When Finished",
            name="delete_temp",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        p10.value = True
        params.append(p10)

        return params

    # --------------------------------------------------------------------------
    def isLicensed(self):
        return True

    # --------------------------------------------------------------------------
    # Create timestamped temp folder next to GDB
    # --------------------------------------------------------------------------
    def _create_temp_folder(self, workspace, messages):
        wp = Path(workspace)
        temp = wp.parent / f"{wp.stem}_Temp_{datetime.now():%Y%m%d_%H%M%S}"
        temp.mkdir(exist_ok=True)
        messages.addMessage(f"Temporary folder created: {temp}")
        return temp

    # --------------------------------------------------------------------------
    # Delete temp folder safely
    # --------------------------------------------------------------------------
    def _delete_temp_folder(self, folder, delete_allowed, messages):
        if not delete_allowed:
            messages.addMessage(f"Temporary folder kept: {folder}")
            return
        folder = Path(folder)
        shutil.rmtree(folder, ignore_errors=True)
        messages.addMessage(f"Temporary folder deleted: {folder}")

    # --------------------------------------------------------------------------
    # Normalize ANY raster input (dataset or layer)
    # --------------------------------------------------------------------------
    def _normalize_raster(self, raster_input, temp_folder, messages):
        desc = arcpy.Describe(raster_input)

        if desc.dataType == "RasterDataset":
            messages.addMessage("Input is a raster dataset.")
            return raster_input

        if desc.dataType == "RasterLayer":
            # Convert layer → TIFF
            out = str(temp_folder / "normalized_input.tif")
            arcpy.management.CopyRaster(raster_input, out)
            messages.addMessage(f"Raster layer converted to dataset: {out}")
            return out

        raise arcpy.ExecuteError("Input is not a valid raster layer or dataset.")

    # --------------------------------------------------------------------------
    # Extract a single band safely
    # --------------------------------------------------------------------------
    def _extract_single_band(self, in_raster, band_index, out_path, messages):
        try:
            arcpy.CheckOutExtension("ImageAnalyst")
            arcpy.ia.ExtractBand(in_raster, [band_index]).save(out_path)
            arcpy.CheckInExtension("ImageAnalyst")
            return out_path
        except:
            # Fallback
            src = f"{in_raster}\\Band_{band_index}"
            arcpy.management.CopyRaster(src, out_path)
            return out_path

    # --------------------------------------------------------------------------
    # MAIN EXECUTE
    # --------------------------------------------------------------------------
    def execute(self, parameters, messages):

        in_raw = parameters[0].valueAsText
        mask = parameters[1].valueAsText if parameters[1].value else None
        workspace = parameters[2].valueAsText
        nclass = int(parameters[3].value)
        min_area = float(parameters[4].value)
        buff_dist = parameters[5].valueAsText
        min_buff_area = float(parameters[6].value)
        out_fc = parameters[7].valueAsText
        blue_band = int(parameters[8].value) if parameters[8].value else 3
        parallel = bool(parameters[9].value)
        delete_temp = bool(parameters[10].value)

        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = workspace
        arcpy.env.cellSize = in_raw
        if parallel:
            arcpy.env.parallelProcessingFactor = "100%"

        temp = self._create_temp_folder(workspace, messages)

        try:
            in_raster = self._normalize_raster(in_raw, temp, messages)

            # Mask
            if mask:
                aerial = str(temp / "aerial_masked.tif")
                arcpy.sa.ExtractByMask(in_raster, mask).save(aerial)
            else:
                aerial = in_raster

            # IsoCluster
            sig = str(temp / "signature.GSG")
            arcpy.sa.IsoCluster(aerial, sig, number_classes=nclass)

            # ML Classify
            classified = arcpy.sa.MLClassify(aerial, sig)

            # Reclassify dead class
            rem = arcpy.sa.RemapValue([[i,"NODATA"] for i in range(1,10)] + [[10,1]])
            dead = str(temp / "dead_class.tif")
            arcpy.sa.Reclassify(classified, "Value", rem).save(dead)

            # Blue band
            blue_tif = str(temp / "blue.tif")
            self._extract_single_band(in_raster, blue_band, blue_tif, messages)

            # Blue threshold
            blue_mask = str(temp / "blue_mask.tif")
            rem2 = arcpy.sa.RemapRange([[0,150,"NODATA"],[150,255,1]])
            arcpy.sa.Reclassify(blue_tif, "Value", rem2).save(blue_mask)

            # Combine
            extracted = str(temp / "extracted.tif")
            arcpy.sa.ExtractByMask(dead, blue_mask).save(extracted)

            # Majority filter
            filtered = str(temp / "filtered.tif")
            arcpy.sa.MajorityFilter(extracted).save(filtered)

            # Expand/Shrink
            expanded = str(temp / "expanded.tif")
            arcpy.sa.Expand(filtered, 1, 1).save(expanded)

            shrinked = str(temp / "shrinked.tif")
            arcpy.sa.Shrink(expanded, 1, 1).save(shrinked)

            # Raster → polygon
            region = arcpy.sa.RegionGroup(shrinked)
            poly = str(temp / "polygons.shp")
            arcpy.conversion.RasterToPolygon(region, poly, "NO_SIMPLIFY")

            # Filter polygons by area
            arcpy.AddField_management(poly, "Area", "DOUBLE")
            arcpy.CalculateField_management(poly, "Area", "!shape.area!")
            selected = str(temp / "selected.shp")
            arcpy.analysis.Select(poly, selected, f"Area>{min_area}")

            # Buffer & dissolve
            buff = str(temp / "buffer.shp")
            arcpy.analysis.Buffer(selected, buff, buff_dist)

            dissolved = str(temp / "dissolved.shp")
            arcpy.management.Dissolve(buff, dissolved, "", "", "SINGLE_PART")

            arcpy.AddField_management(dissolved, "Area", "DOUBLE")
            arcpy.CalculateField_management(dissolved, "Area", "!shape.area!")

            final_temp = str(temp / "final_selected.shp")
            arcpy.analysis.Select(dissolved, final_temp, f"Area>{min_buff_area}")

            # Final output
            arcpy.management.CopyFeatures(final_temp, out_fc)
            messages.addMessage(f"Processing complete! Output saved to: {out_fc}")

        except Exception as e:
            messages.addError(str(e))
            raise

        finally:
            self._delete_temp_folder(temp, delete_temp, messages)
