import arcpy
import os

# Allow overwriting of existing output
arcpy.env.overwriteOutput = True

# Set the workspace
arcpy.env.workspace = r"D:\Luba\chapter3\python_code_workflow"
workspace = r"D:\Luba\chapter3\python_code_workflow\input_images"

# List all files in the workspace directory
all_files = os.listdir(workspace)

# Filter for files with the ".JP2" extension
jp2_files = [file for file in all_files if file.endswith(".JP2")]

# Loop through each JP2 raster file
for jp2_file in jp2_files:
    # Construct the full file path
    jp2_file_path = os.path.join(workspace, jp2_file)
    print(f"Processing JP2 raster: {jp2_file_path}")
    file_name_without_extension = os.path.splitext(jp2_file)[0]
    input_raster = jp2_file_path
    mask_layer = "shrubs_and_forest.tif"
    arcpy.env.cellSize = input_raster

    raster_clipped_forest = arcpy.sa.ExtractByMask(input_raster, mask_layer)

    # Step 2: Iso Cluster tool with 10 classes on the resulting raster
    out_signature_file = "output_signature.GSG"
    arcpy.sa.IsoCluster(raster_clipped_forest, out_signature_file, number_classes=10)

    # Step 3: Maximum likelihood classification with the input signature file
    classified_raster = arcpy.sa.MLClassify(raster_clipped_forest, out_signature_file)

    # Step 4: Reclassify the raster
    remap = arcpy.sa.RemapValue(
        [[1, "NODATA"], [2, "NODATA"], [3, "NODATA"], [4, "NODATA"], [5, "NODATA"], [6, "NODATA"], [7, "NODATA"],
         [8, "NODATA"], [9, "NODATA"], [10, 1]])
    out_classified_raster = arcpy.sa.Reclassify(classified_raster, "Value", remap)
    out_classified_raster.save("dead_trees.tif")

    # Step 5: Extract by red band:
    red_raster = 'red_raster.tif'
    arcpy.management.CreateColorComposite(input_raster, red_raster, 'Band IDs', 'B1', 'B1', 'B1')

    remap = "0 100 NODATA; 100 255 1"
    out_raster = 'red_mask.tif'
    arcpy.ddd.Reclassify(red_raster, 'Value', remap, out_raster, 'True')

    extracted_raster_by_red = arcpy.sa.ExtractByMask("dead_trees.tif", 'red_mask.tif')
    extracted_raster_by_red.save('extracted_raster_by_red.tif')

    # Step 6: Extract by blue band
    arcpy.management.CreateColorComposite(input_raster, 'blue_raster.tif', 'Band IDs', 'B3', 'B3', 'B3')

    remap = "29 150 NODATA; 150 250 1"
    out_raster = 'blue_mask.tif'
    arcpy.ddd.Reclassify('blue_raster.tif', 'Value', remap, out_raster, 'True')
    extracted_raster_both_bands = arcpy.sa.ExtractByMask('extracted_raster_by_red.tif', 'blue_mask.tif')
    extracted_raster_both_bands.save("extracted_raster_both_bands.tif")

    # Step 7: Convert to a vector layer and filter by size
    dead_trees_region = arcpy.sa.RegionGroup('extracted_raster_both_bands.tif')

    arcpy.conversion.RasterToPolygon(dead_trees_region, "dead_trees_vector_{file_name_without_extension}.shp", "NO_SIMPLIFY")

    # Add a new field named "Shape_Area" to store the area
    arcpy.AddField_management("dead_trees_vector.shp", "Shape_Area", "DOUBLE")

    # Calculate the area and populate the "Shape_Area" field
    expression = "!shape.area!"
    arcpy.CalculateField_management("dead_trees_vector.shp", "Shape_Area", expression, "PYTHON")

    in_feature = "dead_trees_vector.shp"
    out_feature = "dead_trees_selected.shp"
    where_clause = "Shape_Area > 2"
    arcpy.analysis.Select("dead_trees_vector.shp", out_feature, where_clause)

    arcpy.management.CopyFeatures("dead_trees_selected.shp", 'dead_trees_selected_copy_{file_name_without_extension}.shp')

    # Step 8: Buffer dead trees, dissolve and filter by size:
    in_features = 'dead_trees_selected_copy_{file_name_without_extension}.shp'
    out_feature_class = 'buffered_trees.shp'
    buffer_distance_or_field = "1 Meters"  # Change the buffer distance as needed
    line_side = "FULL"
    line_end_type = "ROUND"
    # Perform the buffer analysis
    arcpy.analysis.Buffer(in_features, out_feature_class, buffer_distance_or_field, line_side, line_end_type)

    in_buffer = 'buffered_trees.shp'
    dissolved = 'dissolved_buffer.shp'
    arcpy.management.Dissolve(in_buffer, dissolved, "", "", "SINGLE_PART")

    # Add a new field named "Shape_Area" to store the area
    arcpy.AddField_management("dissolved_buffer.shp", "Shape_Area", "DOUBLE")

    # Calculate the area and populate the "Shape_Area" field
    expression = "!shape.area!"
    arcpy.CalculateField_management("dissolved_buffer.shp", "Shape_Area", expression, "PYTHON")

    out_feature = "trees_buffer_processed.shp"
    where_clause = '"Shape_Area">80'
    arcpy.analysis.Select("dissolved_buffer.shp", out_feature, where_clause)

    in_rast = "trees_buffer_processed.shp"
    out_rast = "dead_trees_final_{file_name_without_extension}.shp"
    arcpy.management.CopyFeatures(in_rast, out_rast)

    # Step 9: Spacial join tables:

    input_Molly_points = "Molly_deadtrees.shp"
    #extent_layer = "aerial_image.tif"
    arcpy.env.extent = raster_clipped_forest
    output_clipped = "Molly_points_clipped.shp"
    arcpy.management.CopyFeatures(input_Molly_points, output_clipped)

    target_feature = "dead_trees_final_{file_name_without_extension}.shp"
    join_feature = "Molly_points_clipped.shp"
    out_feature_class = "polygons_to_points.shp"
    arcpy.analysis.SpatialJoin(target_feature, join_feature, out_feature_class)

    target_feature = "Molly_points_clipped.shp"
    join_feature = "dead_trees_final_{file_name_without_extension}.shp"
    out_feature_class = "points_to_polygons.shp"
    arcpy.analysis.SpatialJoin(target_feature, join_feature, out_feature_class)

    # Calculate number rows which had intersection with ground data

    # Specify the input feature classes
    polygons_to_points = "polygons_to_points.shp"
    points_to_polygons = "points_to_polygons.shp"

    # Use the Select tool to select rows where Join_Count is not equal to 0 for polygons_to_points
    arcpy.Select_analysis(polygons_to_points, "selected_polygons_to_points", '"Join_Count" <> 0')

    # Use the Get Count tool to count selected features and total features for polygons_to_points
    TP = int(arcpy.GetCount_management("selected_polygons_to_points").getOutput(0))
    All_polygons = int(arcpy.GetCount_management(polygons_to_points).getOutput(0))
    FN = All_polygons - TP

    # Use the Select tool to select rows where Join_Count is not equal to 0 for points_to_polygons
    arcpy.Select_analysis(points_to_polygons, "selected_points_to_polygons", '"Join_Count" <> 0')

    # Use the Get Count tool to count selected features and total features for points_to_polygons
    TP_2 = int(arcpy.GetCount_management("selected_points_to_polygons").getOutput(0))
    All_points = int(arcpy.GetCount_management(points_to_polygons).getOutput(0))
    FP = All_points - TP_2

    # Print number of intersecting rows
    print(f"Image Label: {file_name_without_extension}")
    print(f"Polygons which had intersecting point: {TP:.2f}")
    print(f"Polygons which did not had intersecting point: {FN:.2f}")
    print(f"All polygons: {All_polygons:.2f}")
    print(f"Points which had intersecting polygons: {TP_2:.2f}")
    print(f"Points which did not had intersecting polygons: {FP:.2f}")
    print(f"All points: {All_points:.2f}")

    # Calculate Precision
    precision = TP / (TP + FP)

    # Calculate Recall
    recall = TP / (TP + FN)

    # Calculate F1-score
    f1_score = 2 * (precision * recall) / (precision + recall)

    # Print the results
    print(f"Precision: {precision:.2f}")
    print(f"Recall: {recall:.2f}")
    print(f"F1-score: {f1_score:.2f}")

    ## Calculate this with TP_2 in place of TP:

    # Calculate Precision
    precision_2 = TP_2 / (TP_2 + FP)

    # Calculate Recall
    recall_2 = TP_2 / (TP_2 + FN)

    # Calculate F1-score
    f1_score_2 = 2 * (precision_2 * recall_2) / (precision_2 + recall_2)

    # Print the results
    print(f"Precision with inverted spatial join: {precision_2:.2f}")
    print(f"Recall with inverted spatial join: {recall_2:.2f}")
    print(f"F1-score with inverted spatial join: {f1_score_2:.2f}")




