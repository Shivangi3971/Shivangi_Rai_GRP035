# KUDA
Pytorch implementation of KUDA. 
> [Prior Knowledge Guided Unsupervised Domain Adaptation](https://arxiv.org/abs/2207.08877)                 
> Tao Sun, Cheng Lu, and Haibin Ling                 
> *ECCV 2022* 


### Knowledge-guided Unsupervised Domain Adaptation (KUDA)
<img src="fig/PK.png" width="90%">

### Integrating rectification module into SHOT and DINE
<img src="fig/framework.png" width=90%>

## Usage
### Prerequisites

We experimented with python environment, pytorch , cudatoolkit & gurobi
we have to install requirement.txt file
pip install -r requirements.txt
For Zero-One programming, we use [Gurobi Optimizer](https://www.gurobi.com/). A free [academic license](https://www.gurobi.com/academia/academic-program-and-licenses/) can be obtained from its official website. 


### Data Preparation
Download the [office31](https://faculty.cc.gatech.edu/~judy/domainadapt/), [Office-Home](https://www.hemanthdv.org/officeHomeDataset.html), [VisDA](https://ai.bu.edu/visda-2017/), [DomainNet](http://ai.bu.edu/M3SDA/) datasets.

Setup dataset path in ./data
```shell

bash data/setup_data_path.sh /data3/Shivangi/dataset/office-home office-home
bash data/setup_data_path.sh /data3/Shivangi/dataset/office31 office31
bash data/setup_data_path.sh /data3/Shivangi/dataset/visda-2017 visda
bash data/setup_data_path.sh /data3/Shivangi/dataset/domainnet40 domainnet40
```

### kSHOT
Unsupervised Closed-set Domain Adaptation (UDA) on the Office-Home dataset 
```shell
cd SHOT

time=`python ../util/get_time.py`
gpu_id=0

# generate source models
for src in "Product" "Clipart" "Art" "Real_World"; do
    echo $src
    python image_source.py --trte val --da uda --gpu_id $gpu_id --dset office-home --max_epoch 50 --s $src --timestamp $time
done

# adapt to other target domains with Unary Bound prior knowledge
for seed in 2020 2021 2022; do
    for src in "Product" "Clipart" "Art" "Real_World"; do
        echo $src
        python image_target_kSHOT.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset office-home --s $src --timestamp $time --pk_uconf 0.0 --seed $seed --pk_type ub
    done
done
```

### kDINE
Unsupervised Closed-set Domain Adaptation (UDA) on the Office-Home dataset 
```shell
cd DINE

time=`python ./get_time.py`
gpu=0

for seed in 2020 2021 2022; do
for src in 'Product' 'Real_World' 'Art' 'Clipart' ; do
      echo $src
      # training the source model first
      python DINE_dist.py --gpu_id $gpu --seed $seed --dset office-home --s $src --da uda --net_src resnet50 --max_epoch 50 --timestamp $time
      # the first step (Distill) with Unary Bound prior knowledge
      python DINE_dist_kDINE.py --gpu_id $gpu --seed $seed  --dset office-home --s $src --da uda --net_src resnet50 --max_epoch 30 --net resnet50  --distill --topk 1 --timestamp $time --pk_type ub --pk_uconf 0.0
      # the second step (Finetune)
      python DINE_ft.py --gpu_id $gpu --seed $seed --dset office-home --s $src --da uda --net_src resnet50 --max_epoch 30 --net resnet50 --lr 1e-2  --timestamp $time --method kdine
done
done
```
Complete commands are available in ./SHOT/run_all_kSHOT.sh and ./DINE/run_all_kDINE.sh.

## Acknowledgements
The implementations are adapted from [SHOT](https://github.com/tim-learn/SHOT) and 
  [DINE](https://github.com/tim-learn/DINE).
  
  
## Citation
If you find our paper and code useful for your research, please consider citing
```bibtex
@inproceedings{sun2022prior,
    author    = {Sun, Tao and Lu, Cheng and Ling, Haibin},
    title     = {Prior Knowledge Guided Unsupervised Domain Adaptation},
    booktitle = {Proceedings of the European Conference on Computer Vision (ECCV)},
    year      = {2022}
}
```# Shivangi_Rai_GRP035
