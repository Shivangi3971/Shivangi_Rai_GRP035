gpu_id=0
time=`python3 ../util/get_time.py`


# office-home ----------------------------------------------------------------------------------------------------------
# for src in "Product" "Clipart" "Art" "Real_World"; do
#     echo $src
#     python3 image_source.py --trte val --da uda --gpu_id $gpu_id --dset office-home --s $src --max_epoch 50 --timestamp $time
# done

for seed in 2020 2021 2022; do
    for src in "Product" "Clipart" "Art" "Real_World"; do
        echo $src
        # for pk_uconf in 0.0 0.1 0.5 1.0 2.0; do
        #     python3 image_target_kSHOT.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset office-home --s $src --timestamp $time --seed $seed --pk_uconf $pk_uconf --pk_type ub
        # done
        python3 image_target.py --cls_par 0.3 --da uda --gpu_id $gpu_id --dset office-home --s $src --timestamp $time --seed $seed
    done
done
 