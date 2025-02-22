# Boosting Adversarial Transferability via Gradient Relevance Attack 

## Requirements

+ Python = 3.6.13
+ Tensorflow = 1.13.1
+ Numpy = 1.16.0
+ opencv = 3.4.2.16
+ scipy = 1.2.0
+ pandas =  1.1.1
+ imageio = 2.8.0

## Setup for requirements in Colab/Kaggle

Install Miniconda in Colab/Kaggle
```
!wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
!chmod +x Miniconda3-latest-Linux-x86_64.sh
!bash ./Miniconda3-latest-Linux-x86_64.sh -b -f -p /usr/local 
```

Add conda to the system path
```
import sys
sys.path.append('/usr/local/lib/python3.7/site-packages')
```
Create and activate conda environment
```
!conda create -n my_env python=3.6.13 -y
!source activate my_env
```
Installing requirements
```
! source activate my_env && pip install numpy==1.16.0 opencv-python==3.4.2.16 scipy==1.2.0 pandas==1.1.1 imageio==2.8.0
! source activate my_env && pip install tensorflow-gpu==1.13.1
```
Install the required cudatoolkit and cudnn
```
! source activate my_env && conda install cudatoolkit=10.0 -y
! source activate my_env && conda install -c conda-forge cudnn -y
```

## Attack

### Prepare the data and models

You should download the [data](https://drive.google.com/drive/folders/1CfobY6i8BfqfWPHL31FKFDipNjqWwAhS) and [pretrained models](https://drive.google.com/drive/folders/10cFNVEhLpCatwECA6SPB-2g0q5zZyfaw) before running the code. Then place the data and pretrained models in dev_data/ and models/, respectively.

### GRA

#### Runing attack

Taking GRA attack for example, you can run this attack as following: (for all the ablations the code is provided in GRA in comments form)
In colab you do not have to add anything after GRA code path, and in kaggle please add the rest of the things along with the path to them as per saved in kaggle datasets and models.
```
! source activate my_env && python3 /path/to/GRA_v3.py --checkpoint_path $checkpoint_path --input_dir $input_dir --output_dir $output_dir --labels_path $labels_path
```

All the provided codes generate adversarial examples on inception_v3 model. If you want to attack other models, replace the model in `graph` and `batch_grad` function and load such models in `main` function.

The generated adversarial examples would be stored in directory `./outputs`. Then run the file `simple_eval.py` to evaluate the success rate of each model used in the paper:

```
! source activate my_env && python3 path/to/simple_eval.py
```
The same is true here add the paths as per required in kaggle.
#### 



