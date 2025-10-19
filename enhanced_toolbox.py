# ------------------------------------------------------------------------------
# Dead Trees Detection Toolbox (.pyt)
# Author: Liubov Dumarevskaya
# Email: luba.dm@gmail.com
# GitHub: https://github.com/LiubovD
# Last Modified: October 19, 2025
#
# Description:
# This ArcGIS Pro Python Toolbox detects likely dead trees from aerial imagery
# using unsupervised raster classification, blue-band thresholding, and
# morphological filtering, followed by vector conversion and size-based cleanup.
#
# License: MIT License
# Copyright (c) 2025 Liubov Dumarevskaya
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# ------------------------------------------------------------------------------

import arcpy
import os
from arcpy.sa import (
    Raster, ExtractByMask, Reclassify, RemapValue, Con,
    MajorityFilter, Expand, Shrink, RegionGroup, IsoClusterUnsupervisedClassification
)

class Toolbox(object):
    def __init__(self):
        self.label = "Dead Trees Detection Toolbox"
        self.alias = "DeadTrees"
        self.tools = [DetectDeadTrees]

class DetectDeadTrees(object):
    def __init__(self):
        self.label = "Detect Dead Trees"
        # Add author/license/meta in description (so it appears in tool help)
        self.description = (
            "Detects likely dead trees from aerial imagery via unsupervised classification, "
            "blue-band thresholding, morphological filtering, vectorization, and area-based cleanup.\n\n"
            "Author: Liubov Dumarevskaya  |  Email: luba.dm@gmail.com  |  GitHub: https://github.com/LiubovD\n"
            "Last Modified: October 19, 2025  |  License: MIT License (c) 2025 Liubov Dumarevskaya"
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        params = []

        # 0) Input raster
        p0 = arcpy.Parameter(
            displayName="Input Aerial Image",
            name="input_raster",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input")
        params.append(p0)

        # 1) Optional forest mask (polygon)
        p1 = arcpy.Parameter(
            displayName="Forest Mask Layer (optional, polygon)",
            name="mask_layer",
            datatype="GPFeatureLayer",
            parameterType="Optional",
            direction="Input")
        p1.filter.list = ["Polygon"]
        params.append(p1)

        # 2) Output workspace (for temp files)
        p2 = arcpy.Parameter(
            displayName="Output Workspace (folder or geodatabase)",
            name="workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")
        params.append(p2)

        # 3) Number of classes
        p3 = arcpy.Parameter(
            displayName="Number of Classes for Classification",
            name="number_classes",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        p3.value = 10
        params.append(p3)

        # 4) Minimum area threshold (m²)
        p4 = arcpy.Parameter(
            displayName="Minimum Tree Area (square meters)",
            name="min_area",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        p4.value = 1.0
        params.append(p4)

        # 5) Buffer distance (meters)
        p5 = arcpy.Parameter(
            displayName="Buffer Distance (meters)",
            name="buffer_distance",
            datatype="GPLinearUnit",
            parameterType="Optional",
            direction="Input")
        p5.value = "1 Meters"
        params.append(p5)

        # 6) Minimum buffer area (m²)
        p6 = arcpy.Parameter(
            displayName="Minimum Buffer Area (square meters)",
            name="min_buffer_area",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        p6.value = 30.0
        params.append(p6)

        # 7) Output feature class (shapefile or FC path)
        p7 = arcpy.Parameter(
            displayName="Output Dead Trees Feature Class",
            name="output_features",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        params.append(p7)

        # 8) Blue band index (optional dropdown) – defaults to 3 at runtime if not set
        p8 = arcpy.Parameter(
            displayName="Blue Band Index (optional)",
            name="blue_band_index",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        # Range filter for convenience (user can still type manually)
        p8.filter.type = "Range"
        p8.filter.list = [1, 15]  # 1..15
        params.append(p8)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        # ---- Read params
        input_raster = parameters[0].valueAsText
        mask_layer = parameters[1].valueAsText
        workspace = parameters[2].valueAsText
        number_classes = int(parameters[3].value) if parameters[3].value is not None else 10
        min_area = float(parameters[4].value) if parameters[4].value is not None else 1.0
        buffer_distance = parameters[5].valueAsText if parameters[5].valueAsText else "1 Meters"
        min_buffer_area = float(parameters[6].value) if parameters[6].value is not None else 30.0
        output_features = parameters[7].valueAsText
        blue_band_index = int(parameters[8].value) if parameters[8].value is not None else 3  # default to 3

        # ---- Env
        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = workspace
        arcpy.env.cellSize = input_raster
        # Tip: You can uncomment the next line to enable multithreading on supported tools.
        # arcpy.env.parallelProcessingFactor = "50%"

        # ---- Validate
        if not arcpy.Exists(input_raster):
            raise arcpy.ExecuteError("Input raster does not exist.")
        if mask_layer and not arcpy.Exists(mask_layer):
            raise arcpy.ExecuteError("Forest mask layer path is invalid or not found.")
        if not arcpy.Exists(workspace):
            raise arcpy.ExecuteError("Workspace does not exist.")

        # Check out Spatial Analyst
        ext_status = arcpy.CheckExtension("Spatial")
        if ext_status != "Available":
            raise arcpy.ExecuteError("Spatial Analyst extension is not available.")
        arcpy.CheckOutExtension("Spatial")

        intermediates = []  # track temp data to delete

        def _tmp(name):
            """Helper to create unique temp paths in the chosen workspace."""
            base = os.path.join(workspace, name)
            # For FileSystem workspace: prefer TIFF; for GDB: dataset name
            if arcpy.Describe(workspace).workspaceType == "FileSystem":
                # For shapefile temps, ensure .shp; for rasters, use .tif
                if name.lower().endswith(".shp"):
                    return base
                return os.path.join(workspace, f"{name}.tif")
            else:
                return base

        try:
            messages.addMessage("Step 1/10: Preparing raster…")
            if mask_layer and mask_layer.strip():
                messages.addMessage("• Forest mask provided — extracting forest area from input raster.")
                aerial_image = _tmp("aerial_image")
                ExtractByMask(input_raster, mask_layer).save(aerial_image)
                intermediates.append(aerial_image)
            else:
                messages.addWarningMessage("• No forest mask provided — proceeding on full extent. "
                                           "Tip: Using a forest polygon mask can speed up processing and reduce false positives.")
                aerial_image = input_raster  # use as-is

            # Step 2: Unsupervised classification (IsoCluster -> classes raster)
            messages.addMessage("Step 2/10: Creating unsupervised classes with IsoCluster…")
            classified_raster = _tmp("classified")
            IsoClusterUnsupervisedClassification(
                aerial_image, number_classes, 1000, 10
            ).save(classified_raster)
            intermediates.append(classified_raster)

            # Step 3: No MLClassify needed (we already have classes)
            messages.addMessage("Step 3/10: Skipping MLClassify (unsupervised classes already created).")

            # Step 4: Reclassify — keep class 10 as dead trees (1), others -> NoData
            messages.addMessage("Step 4/10: Reclassifying to isolate likely dead trees (class 10 -> 1; others -> NoData)…")
            remap = RemapValue([
                [1, "NODATA"], [2, "NODATA"], [3, "NODATA"],
                [4, "NODATA"], [5, "NODATA"], [6, "NODATA"],
                [7, "NODATA"], [8, "NODATA"], [9, "NODATA"],
                [10, 1]
            ])
            dead_trees_raster = _tmp("dead_trees")
            Reclassify(classified_raster, "Value", remap).save(dead_trees_raster)
            intermediates.append(dead_trees_raster)

            # Step 5: Blue-band thresholding (kept even if no forest mask, per your choice)
            messages.addMessage(f"Step 5/10: Blue band check (using Band {blue_band_index})…")
            try:
                # Many raster types can be accessed via Band_{index}
                blue_band = Raster(f"{input_raster}/Band_{blue_band_index}")
            except Exception:
                # Fallback for some datasets
                blue_band = Raster(input_raster)  # last resort; may not be band-separated
                messages.addWarningMessage("• Could not read a specific band path; using the full raster as a fallback for blue band. "
                                           "Consider providing a multiband raster with accessible bands.")

            blue_mask = _tmp("blue_mask")
            # Keep pixels >= 150 as 1, else NoData (tune threshold as appropriate for your sensor/bit-depth)
            Con(blue_band >= 150, 1).save(blue_mask)
            intermediates.append(blue_mask)

            extracted_raster = _tmp("extracted_raster_one_band")
            ExtractByMask(dead_trees_raster, blue_mask).save(extracted_raster)
            intermediates.append(extracted_raster)

            # Step 6: Majority filter
            messages.addMessage("Step 6/10: Applying majority filter to reduce salt-and-pepper noise…")
            filtered_raster = _tmp("filtered")
            MajorityFilter(extracted_raster).save(filtered_raster)
            intermediates.append(filtered_raster)

            # Step 7: Expand then Shrink to connect fragments
            messages.addMessage("Step 7/10: Expanding and shrinking to connect small fragments…")
            expanded_raster = _tmp("expanded")
            Expand(filtered_raster, 1, [1]).save(expanded_raster)  # expand class 1 by 1 cell
            intermediates.append(expanded_raster)

            shrinked_raster = _tmp("shrinked")
            Shrink(expanded_raster, 1, [1]).save(shrinked_raster)  # shrink back
            intermediates.append(shrinked_raster)

            # Step 8: Convert to vector and size filter
            messages.addMessage("Step 8/10: Converting raster to polygons and filtering by area…")
            grouped_raster = _tmp("region_group")
            RegionGroup(shrinked_raster).save(grouped_raster)
            intermediates.append(grouped_raster)

            dead_trees_vector = os.path.splitext(_tmp("dead_trees_vector"))[0] + ".shp"
            arcpy.conversion.RasterToPolygon(grouped_raster, dead_trees_vector, "NO_SIMPLIFY", "VALUE")

            # Ensure area field and calculate
            if "Shape_Area" not in [f.name for f in arcpy.ListFields(dead_trees_vector)]:
                arcpy.management.AddField(dead_trees_vector, "Shape_Area", "DOUBLE")
            arcpy.management.CalculateField(dead_trees_vector, "Shape_Area", "!shape.area!", "PYTHON3")

            dead_trees_selected = os.path.splitext(_tmp("dead_trees_selected"))[0] + ".shp"
            arcpy.analysis.Select(dead_trees_vector, dead_trees_selected, f"\"Shape_Area\" > {min_area}")
            intermediates.extend([dead_trees_vector, dead_trees_selected])

            # Step 9: Buffer + dissolve
            messages.addMessage("Step 9/10: Buffering and dissolving…")
            buffered_trees = os.path.splitext(_tmp("buffered_trees"))[0] + ".shp"
            arcpy.analysis.Buffer(
                dead_trees_selected, buffered_trees, buffer_distance,
                "FULL", "ROUND", "NONE", None, "PLANAR"
            )
            intermediates.append(buffered_trees)

            dissolved_buffer = os.path.splitext(_tmp("dissolved_buffer"))[0] + ".shp"
            arcpy.management.Dissolve(
                buffered_trees, dissolved_buffer, "", "", "SINGLE_PART", "DISSOLVE_LINES"
            )
            if "Shape_Area" not in [f.name for f in arcpy.ListFields(dissolved_buffer)]:
                arcpy.management.AddField(dissolved_buffer, "Shape_Area", "DOUBLE")
            arcpy.management.CalculateField(dissolved_buffer, "Shape_Area", "!shape.area!", "PYTHON3")
            intermediates.append(dissolved_buffer)

            # Step 10: Final selection & output
            messages.addMessage("Step 10/10: Final selection and saving output…")
            trees_buffer_processed = os.path.splitext(_tmp("trees_buffer_processed"))[0] + ".shp"
            arcpy.analysis.Select(dissolved_buffer, trees_buffer_processed, f"\"Shape_Area\" > {min_buffer_area}")

            # Copy to final output
            arcpy.management.CopyFeatures(trees_buffer_processed, output_features)

            # Suggestions (short, practical)
            messages.addMessage("Done! ✅")
            messages.addMessage("Suggestions:")
            messages.addMessage("• If your sensor’s blue band isn’t Band 3 (e.g., Sentinel-2 uses Band 2 for Blue), set the Blue Band Index accordingly.")
            messages.addMessage("• Providing a forest polygon mask can improve precision and speed.")
            messages.addMessage("• Class 10 is assumed as the dead-tree class. If results look off, inspect the classified raster to confirm which class to keep.")
            messages.addMessage("• Consider tuning the blue threshold (currently >= 150) to your data’s radiometry (8/12/16-bit).")

        except arcpy.ExecuteError:
            messages.addErrorMessage(arcpy.GetMessages(2))
            raise
        except Exception as e:
            messages.addErrorMessage(f"Unexpected error: {e}")
            raise
        finally:
            # Auto-clean intermediates (best effort)
            for path in set(intermediates):
                try:
                    if arcpy.Exists(path):
                        arcpy.management.Delete(path)
                except Exception:
                    pass
            try:
                arcpy.CheckInExtension("Spatial")
            except Exception:
                pass
