# Top_db_net_modify


## Source code of Topdbnet_change

### Authors
- [Chih Wei Wu](https://github.com/dddd247)


### Get Started
1. cd the folder where you want to download this repo
2. Run git clone https://github.com/dddd247/Vehicle-Re-ID.git
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
   - VeRi-776
   - VehicleID
   
   You need to download them by yourself, and then create a file to store reid datasets
   under this repo via
    ```bash
    cd Vehicle-Re-ID
    mkdir datasets
    ```
    
    (1) VeRi-776
    * Download the dataset to `dataset/` from https://github.com/JDAI-CV/VeRidataset
    * Extract dataset and rename to `VeRi`. The data structure would like:
    
    ```bash
    datasets
        VeRi # this folder contains 18 files.
            image_query/
            image_test/
            image_train/
            ......
    ```  
    (2) VehicleID
    * Download the dataset to `dataset/` from https://pkuml.org/resources/pku-vehicleid.html
    * Extract dataset and rename to `VehicleID`. The data structure would like:
    
    ```bash
    datasets
        VehicleID # this folder contains 4 files.
            attribute/
            image/
            train_test_split/
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
 
 1. VeRi-776, cross entropy loss + triplet loss
 
 You can directly use the command as follows:
 
 ```bash
python train.py -s veri -t veri --height 128 --width 256 --optim amsgrad --lr 0.0003 --gamma 0.1 --random_erase --color_jitter --color_aug --label_smooth --max_epoch 90 --stepsize 30 55 70 --train_batch_size 48 --test_batch_size 100 -a resnet50_fc2432_bam  --save_dir {the place where you want to save the weights} --gpu_devices 0 --eval_freq 1 --num_instances 8 --workers 8
```

2. VehicleID, cross entropy loss + triplet loss

 You can directly use the command as follows:
 
```bash
python train.py -s vehicleID -t vehicleID --height 128 --width 256 --optim amsgrad --lr 0.0001 --gamma 0.1 --random_erase --color_jitter --color_aug --label_smooth --max_epoch 90 --stepsize 30 55 70 --train_batch_size 48 --test_batch_size 100 -a resnet50_fc2432_bam  --save_dir {the place where you want to save the weights} --gpu_devices 0 --eval_freq 1 --num_instances 8 --workers 8
```


## Test 
You can test your model's performance directly by using these commands as follows:

1. Test with VeRi-776

```bash
python train.py -s veri -t veri --height 128 --width 256 --test_batch_size 100 --evaluate -a resnet50_fc2432_bam --load_weights {the place where you already saved model's weights} --save_dir log/Veri_eval-veri-to-veri --gpu_devices 0  
```

2. Test with VehicleID

```bash
python train.py -s vehicleID -t vehicleID --height 128 --width 256 --test_batch_size 100 --evaluate -a resnet50_fc2432_bam --load_weights {the place where you already saved model's weights} --save_dir log/Veri_eval-vehicleID-to-vehicleID --gpu_devices 0  
```


#### useful tips
If you want to train or test on VehicleID dataset, you need to change the ` eval_metrics.py ` in line 130 in order to match different dataset settings.
