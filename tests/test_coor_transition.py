from pylab_dk.auxiliary import Flakes

Flakes.coor_transition(ref1=(-1, 0), ref1_new=(1, 1),
                       ref2=(0, -1), ref2_new=(2, 2),
                       target=(0, 0))

# Expected output:
# magnitude(length) ratio(new/old):100.0 %
# rot_angle:90.0
# disp:(2,1)
# coor in prac axes:1.0,2.0

Flakes.gui_coor_transition()
# generate a window to input the coordinates of the reference points and the target point.
