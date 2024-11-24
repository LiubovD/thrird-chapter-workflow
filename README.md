# Mapping Individual Dead Trees in Rhode Island

This project utilizes advanced GIS and remote sensing techniques to automatically classify and map individual dead trees from summertime aerial imagery in Rhode Island. 
It aims to support forest health monitoring and management by providing precise geospatial data on tree mortality.

Nessesary input files:
1) high-resolution aerial imagery which will be used for the mapping
2) shrub and forest tiff file which will be used as a mask to clip aerial imagery

Features:
Automated Classification: Uses Iso Cluster and Maximum Likelihood Classification tools to classify aerial imagery.

Resulting file:
Detected dead tree buffers

Accuracy assesment at the end compare hand-digitized trees with automatically detected.
Calculates precision, recall, and F1 scores by comparing classified features with ground truth data.
