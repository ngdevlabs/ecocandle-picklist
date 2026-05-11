# v1.0.0 [03-05-2026]

## Added
- a folder under data by the name of demo 
- data/
    |-- demo/
        |-- all-product.csv
        |-- product-to-picklist.csv
- file is exact replica for the original pick-list files but for sandbox store and on smaller scale of only 2 products and 4 options

## v1.0.0 [04-05-2026]

## Added
- csvtojson.py formats the csv file to a clean json for processing
- topicklist.py using the newly form json file to create picklist and remove the previous dropdowns
- todropdown.py incase of any error reverts the products back to dropdown