#!/bin/bash

gpu_id=0
time=`python ../util/get_time.py`


# domainnet40 ----------------------------------------------------------------------------------------------------------
# for src in "sketch" "clipart" "painting" "real"; do
#     echo $src
#     python image_source.py --trte val --da uda --gpu_id $gpu_id --dset domainnet40 --s $src --max_epoch 50 --timestamp $time
# done

for seed in 2020 2021 2022; do
    for src in "sketch" "clipart" "painting" "real"; do
        echo $src
        # for pk_uconf in 0.0 0.1 0.5 1.0 2.0; do
        #     python image_target_kSHOT.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset domainnet40 --s $src --timestamp $time --seed $seed --pk_uconf $pk_uconf --pk_type ub
        # done
        python image_target.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset domainnet40 --s $src --timestamp $time --seed $seed
    done
done
