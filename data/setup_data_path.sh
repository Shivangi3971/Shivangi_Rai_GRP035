# sh setup_data_path.sh data_path dataset
# bash data/setup_data_path.sh /data3/Shivangi/dataset/office-home office-home
# bash data/setup_data_path.sh /data3/Shivangi/dataset/office31 office31
# bash data/setup_data_path.sh /data3/Shivangi/dataset/visda-2017 visda
# bash data/setup_data_path.sh /data3/Shivangi/dataset/domainnet40 domainnet40


data_path=$1
dataset=$2

if [[ ${dataset} == "domainnet40"  ]] ;
then
  # cd /data3/Shivangi/dataset/domainnet40
  # ln -sfn "${data_path}/clipart" clipart
  # # ln -sfn "${data_path}/infograph" infograph
  # ln -sfn "${data_path}/painting" painting
  # # ln -sfn "${data_path}/quickdraw" quickdraw
  # ln -sfn "${data_path}/real" real
  # ln -sfn "${data_path}/sketch" sketch
  cd /data3/Shivangi/dataset/domainnet40
  rm clipart
  ln -s "${data_path}/clipart" clipart
  # rm infograph
  # ln -s "${data_path}/infograph" infograph
  rm painting
  ln -s "${data_path}/painting" painting
  # rm quickdraw
  # ln -s "${data_path}/quickdraw" quickdraw
  rm real
  ln -s "${data_path}/real" real
  rm sketch
  ln -s "${data_path}/sketch" sketch
  cd ..
elif [[ ${dataset} == "office31"  ]] ;
then
  cd /data3/Shivangi/dataset/office31
  rm amazon
  ln -s "${data_path}/amazon" amazon
  rm webcam
  ln -s "${data_path}/webcam" webcam
  rm dslr
  ln -s "${data_path}/dslr" dslr
elif [[ ${dataset} == "office-home"  ]] ;
then
  cd /data3/Shivangi/dataset/office-home
  rm Art
  ln -s "${data_path}/Art" Art
  rm Clipart
  ln -s "${data_path}/Clipart" Clipart
  rm Product
  ln -s "${data_path}/Product" Product
  rm Real_World
  ln -s "${data_path}/Real_World" Real_World
elif [[ ${dataset} == "office-home-rsut"  ]] ;
then
  cd /data3/Shivangi/dataset/office-home-rsut
  rm Art
  ln -s "${data_path}/Art" Art
  rm Clipart
  ln -s "${data_path}/Clipart" Clipart
  rm Product
  ln -s "${data_path}/Product" Product
  rm Real_World
  ln -s "${data_path}/Real_World" Real_World
elif [[ ${dataset} == "visda"  ]] ;
then
  cd /data3/Shivangi/dataset/visda-2017
  rm training
  ln -s "${data_path}/train" train
  rm validation
  ln -s "${data_path}/validation" validation
fi
cd ..s
