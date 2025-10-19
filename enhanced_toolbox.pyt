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

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Dead Trees Detection Toolbox"
        self.alias = "DeadTrees"

        # List of tool classes associated with this toolbox
        self.tools = [DetectDeadTrees]

class DetectDeadTrees(object):
    def __init__(self):
        """Define the tool (tool name is the class name)."""
        self.label = "Detect Dead Trees"
        self.description = "Detects dead trees from aerial imagery using classification and filtering techniques"
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        params = []
        
        # Input raster parameter
        param0 = arcpy.Parameter(
            displayName="Input Aerial Image",
            name="input_raster",
            datatype="DERasterDataset",
            parameterType="Required",
            direction="Input")
        params.append(param0)
        
        # Forest mask parameter (optional polygons only)
        param1 = arcpy.Parameter(
            displayName="Forest Mask Layer",
            name="mask_layer",
            datatype="GPFeatureLayer",
            parameterType="Optional",
            direction="Input")
        param1.filter.list = ["Polygon"]
        params.append(param1)
        
        # Output workspace
        param2 = arcpy.Parameter(
            displayName="Output Workspace",
            name="workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")
        params.append(param2)
        
        # Number of classes
        param3 = arcpy.Parameter(
            displayName="Number of Classes for Classification",
            name="number_classes",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param3.value = 10
        params.append(param3)
        
        # Minimum area threshold
        param4 = arcpy.Parameter(
            displayName="Minimum Tree Area (square meters)",
            name="min_area",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        param4.value = 1.0
        params.append(param4)
        
        # Buffer distance
        param5 = arcpy.Parameter(
            displayName="Buffer Distance (meters)",
            name="buffer_distance",
            datatype="GPLinearUnit",
            parameterType="Optional",
            direction="Input")
        param5.value = "1 Meters"
        params.append(param5)
        
        # Minimum buffer area
        param6 = arcpy.Parameter(
            displayName="Minimum Buffer Area (square meters)",
            name="min_buffer_area",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        param6.value = 30.0
        params.append(param6)
        
        # Output feature class
        param7 = arcpy.Parameter(
            displayName="Output Dead Trees Feature Class",
            name="output_features",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")
        params.append(param7)

        # Blue band index (optional dropdown) – defaults to 3 if not set
        p8 = arcpy.Parameter(
            displayName="Blue Band Index (optional)",
            name="blue_band_index",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        p8.filter.type = "Range"
        p8.filter.list = [1, 15]  # allow 1..15
        params.append(p8)

        # Enable parallel processing (checkbox), default ON
        p9 = arcpy.Parameter(
            displayName="Enable parallel processing",
            name="enable_parallel",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        p9.value = True
        params.append(p9)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool parameter."""
        return

    def _extract_single_band(self, in_raster, band_index, out_path, messages):
        """
        Extract a single band from a multiband raster to out_path.
        Tries Image Analyst's ExtractBand first; falls back to direct band path.
        """
        # Try Image Analyst ExtractBand
        try:
            arcpy.CheckOutExtension("ImageAnalyst")
            band = arcpy.ia.ExtractBand(in_raster, [band_index])
            band.save(out_path)
            messages.addMessage(f"Selected band {band_index} extracted via Image Analyst to: {out_path}")
            try:
                arcpy.CheckInExtension("ImageAnalyst")
            except Exception:
                pass
            return out_path
        except Exception as e:
            messages.addWarning(f"Image Analyst not available or failed to extract band: {e}. Falling back to band path method.")

        # Fallback: direct band path (works for most formats like .tif)
        band_path = f"{in_raster}\\Band_{band_index}"
        arcpy.management.CopyRaster(band_path, out_path)
        messages.addMessage(f"Selected band {band_index} copied from {band_path} to: {out_path}")
        return out_path

    def execute(self, parameters, messages):
        """The source code of the tool."""
        
        # Get parameters
        input_raster = parameters[0].valueAsText
        mask_layer = parameters[1].valueAsText if parameters[1].valueAsText else None
        workspace = parameters[2].valueAsText
        number_classes = int(parameters[3].value) if parameters[3].value else 10
        min_area = float(parameters[4].value) if parameters[4].value else 1.0
        buffer_distance = parameters[5].valueAsText if parameters[5].valueAsText else "1 Meters"
        min_buffer_area = float(parameters[6].value) if parameters[6].value else 30.0
        output_features = parameters[7].valueAsText

        # Dynamic band selection with safe default
        blue_band_index = int(parameters[8].value) if parameters[8].value else 3

        # Local multi-core parallelism (no GPU, per user instruction)
        enable_parallel = bool(parameters[9].value) if parameters[9].value is not None else True

        # Set environments
        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = workspace
        arcpy.env.cellSize = input_raster
        if enable_parallel:
            arcpy.env.parallelProcessingFactor = "100%"
            messages.addMessage("Parallel processing enabled: arcpy.env.parallelProcessingFactor = '100%'")

        # Validate band index against raster band count
        try:
            band_count = getattr(arcpy.Describe(input_raster), "bandCount", 1)
        except Exception:
            band_count = 1

        if band_count and (blue_band_index < 1 or blue_band_index > band_count):
            messages.addWarning(
                f"Requested band index {blue_band_index} is out of range (1..{band_count}). Defaulting to 3."
            )
            blue_band_index = 3

        try:
            # Step 1: Extract by mask (optional)
            arcpy.AddMessage("Step 1/10: Preparing raster...")

            if mask_layer:
                arcpy.AddMessage("Forest mask provided — extracting forest area from input raster...")
                raster_clipped_forest = arcpy.sa.ExtractByMask(input_raster, mask_layer)
                aerial_image = os.path.join(workspace, "aerial_image.tif")
                raster_clipped_forest.save(aerial_image)
            else:
                arcpy.AddMessage("No forest mask provided — using full input raster.")
                aerial_image = input_raster
            
            # Step 2: Iso Cluster classification
            arcpy.AddMessage("Step 2/10: Performing Iso Cluster classification...")
            out_signature_file = os.path.join(workspace, "output_signature.GSG")
            arcpy.sa.IsoCluster(aerial_image, out_signature_file, number_classes=number_classes)
            
            # Step 3: Maximum likelihood classification
            arcpy.AddMessage("Step 3/10: Performing maximum likelihood classification...")
            classified_raster = arcpy.sa.MLClassify(aerial_image, out_signature_file)
            
            # Step 4: Reclassify (keep only class 10 as dead trees)
            arcpy.AddMessage("Step 4/10: Reclassifying raster...")
            remap = arcpy.sa.RemapValue([[1, "NODATA"], [2, "NODATA"], [3, "NODATA"], 
                                         [4, "NODATA"], [5, "NODATA"], [6, "NODATA"], 
                                         [7, "NODATA"], [8, "NODATA"], [9, "NODATA"], 
                                         [10, 1]])
            out_classified_raster = arcpy.sa.Reclassify(classified_raster, "Value", remap)
            dead_trees_raster = os.path.join(workspace, "dead_trees.tif")
            out_classified_raster.save(dead_trees_raster)
            
            # Step 5: Extract by selected band (was Blue band; now selectable)
            arcpy.AddMessage("Step 5/10: Processing selected band...")
            blue_raster = os.path.join(workspace, "blue_raster.tif")

            # Use helper to extract the chosen band to a single-band raster
            self._extract_single_band(input_raster, blue_band_index, blue_raster, messages)

            # Build a mask from the selected band by reclassifying values
            blue_mask = os.path.join(workspace, "blue_mask.tif")

            # Keep the original thresholds idea: low values -> NODATA, high values -> 1
            # Using RemapRange to mirror "29 150 NODATA; 150 250 1"
            remap_range = arcpy.sa.RemapRange([[0, 150, "NODATA"], [150, 255, 1]])
            out_mask = arcpy.sa.Reclassify(blue_raster, "Value", remap_range, "NODATA")
            out_mask.save(blue_mask)
            
            extracted_raster = os.path.join(workspace, "extracted_raster_one_band.tif")
            extracted_raster_both_bands = arcpy.sa.ExtractByMask(dead_trees_raster, blue_mask)
            extracted_raster_both_bands.save(extracted_raster)
            
            # Step 6: Filtering
            arcpy.AddMessage("Step 6/10: Applying majority filter...")
            filtered_raster = os.path.join(workspace, "filtered_raster.tif")
            (arcpy.sa.MajorityFilter(extracted_raster)).save(filtered_raster)
            
            # Step 7: Expand and shrink
            arcpy.AddMessage("Step 7/10: Expanding and shrinking to connect fragments...")
            expanded_raster = os.path.join(workspace, "expanded_raster.tif")
            (arcpy.sa.Expand(filtered_raster, 1, 1)).save(expanded_raster)
            
            shrinked_raster = os.path.join(workspace, "shrinked_raster.tif")
            (arcpy.sa.Shrink(expanded_raster, 1, 1)).save(shrinked_raster)
            
            # Step 8: Convert to vector and filter by size
            arcpy.AddMessage("Step 8/10: Converting to vector and filtering by size...")
            dead_trees_region = arcpy.sa.RegionGroup(shrinked_raster)
            
            dead_trees_vector = os.path.join(workspace, "dead_trees_vector.shp")
            arcpy.conversion.RasterToPolygon(dead_trees_region, dead_trees_vector, "NO_SIMPLIFY")
            
            arcpy.AddField_management(dead_trees_vector, "Shape_Area", "DOUBLE")
            expression = "!shape.area!"
            arcpy.CalculateField_management(dead_trees_vector, "Shape_Area", expression, "PYTHON")
            
            dead_trees_selected = os.path.join(workspace, "dead_trees_selected.shp")
            where_clause = f"Shape_Area > {min_area}"
            arcpy.analysis.Select(dead_trees_vector, dead_trees_selected, where_clause)
            
            # Step 9: Buffer and dissolve
            arcpy.AddMessage("Step 9/10: Buffering and dissolving...")
            buffered_trees = os.path.join(workspace, "buffered_trees.shp")
            arcpy.analysis.Buffer(dead_trees_selected, buffered_trees, buffer_distance, "FULL", "ROUND")
            
            dissolved_buffer = os.path.join(workspace, "dissolved_buffer.shp")
            arcpy.management.Dissolve(buffered_trees, dissolved_buffer, "", "", "SINGLE_PART")
            
            arcpy.AddField_management(dissolved_buffer, "Shape_Area", "DOUBLE")
            arcpy.CalculateField_management(dissolved_buffer, "Shape_Area", expression, "PYTHON")
            
            # Step 10: Final selection and output
            arcpy.AddMessage("Step 10/10: Creating final output...")
            trees_buffer_processed = os.path.join(workspace, "trees_buffer_processed.shp")
            where_clause = f'"Shape_Area" > {min_buffer_area}'
            arcpy.analysis.Select(dissolved_buffer, trees_buffer_processed, where_clause)
            
            # Copy to final output location
            arcpy.management.CopyFeatures(trees_buffer_processed, output_features)
            
            arcpy.AddMessage(f"Processing complete! Output saved to: {output_features}")
            
        except Exception as e:
            arcpy.AddError(f"Error occurred: {str(e)}")
            raise
