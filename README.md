# Mapping Individual Dead Trees in Rhode Island

This project utilizes advanced GIS and remote sensing techniques to automatically classify and map individual dead trees from summertime aerial imagery in Rhode Island. 
It aims to support forest health monitoring and management by providing precise geospatial data on tree mortality.

Data:
1) Aerial imagery in .tif format.
2) Forest cover mask layer (.shp or .gdb).

Features:
Automated Classification: Uses Iso Cluster and Maximum Likelihood Classification tools to classify aerial imagery.

Resulting file:
Detected dead tree buffers

Accuracy assesment at the end compare hand-digitized trees with automatically detected.
Calculates precision, recall, and F1 scores by comparing classified features with ground truth data.
