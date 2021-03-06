#!/bin/bash -x


eta_list=(5e-4 1e-4 5e-5)
etadecay_list=(1e-5)
lambda_list=(0.5 1.0 1.5 2.0)
timewindow_list=(4)

midoutputsize=20
midoutput2size=10
outputsize=4
FOLDER_NAME=/home/dpark/hrl_file_server/dpark_data/anomaly/RSS2016/pushing_data/${midoutputsize}_${midoutput2size}_${outputsize}
mkdir -p $FOLDER_NAME

for i in "${eta_list[@]}"
do
    for j in "${etadecay_list[@]}"
    do
        for k in "${lambda_list[@]}"
        do
            for l in "${timewindow_list[@]}"
            do

                FILENAME=${FOLDER_NAME}/E_${i}_ED_${j}_L_${k}_TW_${l}.log

                timeout 1200s th run.lua -model three -midoutputsize ${midoutputsize} -midoutput2size ${midoutput2size} -outputsize ${outputsize} -lambda ${k} -eta ${i} -etadecay ${j} -batchsize 16 -timewindow ${l} >> $FILENAME

            done
        done
    done
done
