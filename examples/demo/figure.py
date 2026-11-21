import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(4, 2.4), dpi=200)
ax.bar(['WT', 'dpsA', 'rpoS', 'hfq'], [120, 85, 150, 95], color='#009E73')
ax.set_ylabel('expr fpkm')
ax.set_xlabel('genotype')
fig.savefig('figure.png', bbox_inches='tight')
