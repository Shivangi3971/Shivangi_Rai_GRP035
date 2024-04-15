gpu_id=0
time=`python3 ../util/get_time.py`


# visda-2017 -----------------------------------------------------------------------------------------------------------
python image_source.py --trte val --da uda --gpu_id $gpu_id --dset visda-2017 --s train --max_epoch 10 --timestamp $time --net resnet101 --lr 1e-3

for seed in 2020 2021 2022; do
    # for pk_uconf in 0.0 0.1 0.5 1.0 2.0; do
    #     python image_target_kSHOT.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset visda-2017 --s train --timestamp $time --seed $seed --pk_uconf $pk_uconf --net resnet101 --lr 1e-3 --pk_type ub
    # done
    python image_target_kSHOT.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset visda-2017 --s train --timestamp $time --seed $seed --pk_uconf 1.0 --net resnet101 --lr 1e-3 --pk_type br
done

