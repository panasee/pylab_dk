"""
This file is for tex rendering matplotlib plots, using pgf backend. Could render Chinese characters.
Note that pgf backend will not produce figures directly, use savefig to save the figures
"""
import matplotlib.pyplot as plt
import matplotlib as mpl


mpl.use("pgf")
plt.rcParams.update({
    'text.usetex': True,
    "font.family": "serif",  # use serif/main font for text elements
    "font.serif": "Times New Roman, SimSun",  #use multiple fonts, take care of the search order
    # Arial is widely used as a sans-serif font
    "pgf.texsystem": "xelatex",
    "pgf.rcfonts": False,    # don't setup fonts from rc parameters
#    "text.latex.preamble": "\n".join([
    "pgf.preamble": "\n".join([
         r"\usepackage{ctex}",
         r"\usepackage{fontspec}",
         r"\usepackage{bm}",
         r"\usepackage{amsmath}",
         r"\usepackage{amssymb}",
         r"\usepackage{newtxmath}",
#         r"\usepackage{newtxtext}",
#         r"\usepackage[lite,subscriptcorrection,slantedGreek,nofontinfo]{mtpro2}",
         r"\setmainfont{Times New Roman}",  # serif font via preamble
         r"\setCJKmainfont{SimSun}",  # serif font via preamble
    ]),
    #'mathtext.rm': 'serif',
    #'mathtext.it': 'serif:italic',
    #'mathtext.bf': 'serif:bold',
    'mathtext.fontset': 'stix', # 'cm' is the default font of LaTeX

    # the following bold settings don't work in tex cases
    #'font.weight': 'bold',
    #'axes.labelweight': 'bold',
    'font.size': 11.5,
    'text.antialiased': True,
    'figure.dpi': 300,
    'savefig.dpi': 300,
   
    'xtick.direction': 'in',
    'ytick.direction': 'in',
   
    'xtick.labelsize': 11.5,
    'ytick.labelsize': 11.5,
   
    'xtick.top': True,
    'xtick.bottom': True,
    'ytick.left': True,
    'ytick.right': True,
   
    'xtick.major.size': 4,
    'xtick.minor.size': 1.5,
    'ytick.major.size': 4,
    'ytick.minor.size': 1.5,
    'xtick.minor.visible': False,
    'ytick.minor.visible': False,
   
    'xtick.major.width': 0.7,
    'ytick.major.width': 0.7,
    'xtick.minor.width': 0.5,
    'ytick.minor.width': 0.5,
   
    'axes.linewidth': 0.7,
    #'axes.formatter.limits': -3, 4,
   
    'axes.spines.left': True,
    'axes.spines.right': True,
    'axes.spines.bottom': True,
    'axes.spines.top': True

})

# define font dicts for modifiable legends' "prop" parameter
# thus to allow different font settings for legends
legend_font = {'family': 'Times New Roman', 'weight':'normal', 'size': 8}
#legend_font_tiny = {'family': 'Times New Roman', 'weight':'normal', 'size': 8}


## Use this commands title to plot
#fig, ax = plt.subplots(1,1,figsize=(8.3 * cm_to_inch, 8.3 * cm_to_inch))  # 8.3 for single column, 17.6 for double column(at most 20cm high)
#fig.subplots_adjust(left=.19, bottom=.13, right=.97, top=.85)
# adjust the margin according to the saved fig(not in jupyter), just to assure the display of labels 