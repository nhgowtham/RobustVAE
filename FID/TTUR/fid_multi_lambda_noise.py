import subprocess


cmd = [ "python", \
        "fid.py", \
        "./fid_precalc/fid_stats_lambda_0.1noise_0.0.npz", \
        "./fid_precalc/fid_stats_lambda_0.1noise_0.0.npz", \
        ]


retval = subprocess.call(cmd, 0, None, None, None, None)
print (retval)