#!/bin/bash
#SBATCH -N 1
#SBATCH -n 16
#SBATCH --mem=64G
#SBATCH -p short

sacct --format="CPUTime,MaxRSS"
python ../BasicAutoencoder/DeepVAE2.py
