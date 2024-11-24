import arcpy

# Allow overwriting of existing output
arcpy.env.overwriteOutput = True

# Set the workspace
arcpy.env.workspace = r"D:\Luba\chapter3\python_code_workflow\input_images\across_RI"

# # Step 1: Iso Cluster tool with 10 classes on the resulting raster
input_raster = r"D:\Luba\chapter3\python_code_workflow\input_images\across_RI\13_RISTAT055013OrthoSectorTile3.tif"


# Use the tool to create random points
num_points = 13
min_distance = "60 meters"
arcpy.management.CreateRandomPoints(arcpy.env.workspace, "RandomPoints_13", "", input_raster, num_points, min_distance)


# Define the parameters for the "Buffer" tool
test_rounds = "rounds"  # Output feature class name for the circular buffer
buffer_radius = "25 meters"  # Desired radius of the circular buffer

# Use the tool to create a circular buffer around the random points
arcpy.analysis.Buffer("RandomPoints_13", "buffer_13", buffer_radius)


