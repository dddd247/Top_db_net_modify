# Top_db_net_modify


## Source code of Topdbnet_change

### Authors
- [Chih Wei Wu](https://github.com/dddd247)


### Get Started
1. cd the folder where you want to download this repo
2. Run git clone https://github.com/dddd247/Top_db_net_modify
3. Install dependencise:
   * python >= 3.6
   * pytorch >= 0.4
   * opencv-contrib-python >= 3.4.1.15
   * opencv-python >= 3.4.1.15
   * colorsys
   * time
   * scipy
   * math
   * numpy
   * os, sys
   * visdom ( help us to visualize the process of training)
4. Prepare dataset:
   - Market1501
   - Dukemtmc
   
   You need to download them by yourself, and then create a file to store reid datasets
   under this repo via
    ```bash
    cd Top_db_net_modify
    mkdir datasets
    ```
    
    (1) Market1501
    * Download the dataset to `dataset/` from https://www.kaggle.com/pengcw1/market-1501
    * Extract dataset and rename to `Market1501`. The data structure would like:
    
    ```bash
    datasets
        Market1501 # this folder contains 6 files.
            bounding_box_test/
            bounding_box_train/
            gt_bbox/
            ......
    ```  
    (2) DukeMTMC
    * Download the dataset to `dataset/` from https://drive.google.com/file/d/1jjE85dRCMOgRtvJ5RQV9-Afs-2_5dY3O/view
    * Extract dataset and rename to `DukeMTMC`. The data structure would like:
    
    ```bash
    datasets
        DukeMTMC# this folder contains 7 files.
            bounding_box_test/
            bounding_box_train/
            query/
            ......
    ```  
    
 5. Prepare the pretrained model if you don't have
        
    （1）ResNet

         ```python
         from torchvision import models
         models.resnet50(pretrained=True)
         ```
         
         
 ## Train
 You can run these command in `args.py ` for training different datasets of different losses.
 
 1. Market1501, cross entropy loss + triplet loss
 
 You can directly use the command as follows:
 
 ```bash
python main.py --config-file configs/Modify_top_bdnet_train_market1501.yaml --root $path_to_datasets
```

2. DukeMTMC, cross entropy loss + triplet loss

 You can directly use the command as follows:
 
```bash
python main.py --config-file configs/Modify_top_bdnet_train_dukemtmc.yaml --root $path_to_datasets
```


## Test 
You can test your model's performance directly by using these commands as follows:

1. Test with Market1501

```bash
python main.py --config-file configs/Modify_top_bdnet_test_market1501.yaml --root $path_to_datasets
```

2. Test with DukeMTMC

```bash

python main.py --config-file configs/Modify_top_bdnet_test_dukemtmc.yaml --root $path_to_datasets  
```


#### useful tips
If you want to show the testing activation maps, you can use make the `visrankactivthr: True` and `visrankactiv: True` on the config files.
