"""Standalone descriptive breadth figure; no invented uncertainty intervals."""
import hashlib
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def plot(root):
    report=json.loads((root/'report.json').read_text())
    if report.get('benign') is not True or report.get('stage')!='breadth' or report.get('state')!='complete':
        raise ValueError('A complete benign breadth report is required')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'pdf.fonttype':42,'svg.fonttype':'none','svg.hashsalt':'repel-breadth-v1'})
    colors={'glm':'#607d9c','deepseek':'#167767'}; names={'glm':'GLM','deepseek':'DeepSeek'}
    fig,axes=plt.subplots(1,3,figsize=(12,5),gridspec_kw={'width_ratios':[1,1.3,1]})
    fig.subplots_adjust(left=.08,right=.97,top=.77,bottom=.25,wspace=.68)
    for axis in axes:
        axis.tick_params(length=0,pad=6); axis.set_axisbelow(True)
        for side,spine in axis.spines.items(): spine.set_visible(side=='bottom'); spine.set_color('#ccd3d8'); spine.set_linewidth(.6)
        axis.grid(axis='x',color='#e3e7eb',linewidth=.55)
    for axis in axes[:2]: axis.set_xlim(-4,104); axis.set_xticks([0,25,50,75,100]); axis.set_xlabel('Verified success (%)',labelpad=11)
    primary=axes[0]
    for y,row in enumerate(report['metrics']):
        x=row['verified_rate']*100
        primary.plot([x,row['acceptance_rate']*100],[y,y],color=colors[row['model']],linewidth=.9)
        primary.scatter([row['acceptance_rate']*100],[y],facecolor='white',edgecolor=colors[row['model']],s=33,zorder=3)
        primary.scatter([x],[y],color=colors[row['model']],edgecolor='white',s=33,zorder=4)
        primary.annotate(f"{row['verified']}/{row['n']} verified",(x,y),xytext=(0,13),textcoords='offset points',ha='center',fontsize=8)
    primary.set_yticks(range(len(report['metrics'])),[names[r['model']] for r in report['metrics']]); primary.set_ylim(-.8,1.8)
    primary.set_title('A  Overall pipeline outcomes',loc='left',pad=19,fontsize=10)
    families=[g for g in report['groups'] if g['dimension']=='family']
    labels={'ceil_div':'Ceiling division','longest_run':'Increasing runs','parse_decimal':'Decimal parsing','temperature':'Temperatures','invoice':'Invoices','schedule':'Intervals','binary-graph':'Binary metadata'}
    for y,group in enumerate(families):
        for row in group['metrics']:
            dy=-.12 if row['model']=='glm' else .12
            axes[1].scatter(row['verified_rate']*100,y+dy,color=colors[row['model']],edgecolor='white',s=29,zorder=3)
    axes[1].set_yticks(range(len(families)),[labels[g['value']] for g in families]); axes[1].set_ylim(-.6,len(families)-.4)
    axes[1].set_title('B  Shared task families',loc='left',pad=19,fontsize=10)
    repositories=report['integration']['repositories']; size=axes[2]; size.set_xscale('log')
    for y,repo in enumerate(repositories):
        value=repo['inventory']['source_lines']; size.scatter(value,y,s=27,color='#6b7787',edgecolor='white',zorder=3)
        size.annotate(f'{value:,}',(value,y),xytext=(0,11),textcoords='offset points',ha='center',fontsize=8)
    size.set_yticks(range(len(repositories)),[r['id'] for r in repositories]); size.set_ylim(-.7,len(repositories)-.3)
    size.set_xlim(10000,1000000); size.set_xticks([10000,100000,1000000],['10k','100k','1m']); size.minorticks_off()
    size.set_xlabel('Physical source lines · log scale',labelpad=11); size.set_title('C  Pinned integration projects',loc='left',pad=19,fontsize=10)
    handles=[Line2D([0],[0],marker='o',color='none',markerfacecolor=colors[m],markeredgecolor='white',label=names[m],markersize=6) for m in ['glm','deepseek']]
    handles += [Line2D([0],[0],marker='o',color='none',markerfacecolor='white',markeredgecolor='#6b7787',label='CLI acceptance (panel A)',markersize=5)]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.12),ncol=3,frameon=False)
    fig.suptitle('Benign generation across languages, formats, and codebase sizes',x=.025,y=.97,ha='left',fontsize=13)
    fig.text(.025,.89,f"{report['counts']['completed']} generations · {len(report['design']['formats'])} targets · two attempts maximum · unchanged frozen primary outcomes",fontsize=9,color='#59626d')
    fig.text(.025,.025,'63 task-format units reuse seven authored families; one replicate per model/unit. Descriptive results, no population confidence interval.\n'
             'Integration covers specified consumer interfaces in three C projects, not whole-repository placement. Source-line counts include comments and blanks.',fontsize=7,color='#59626d',linespacing=1.6)
    hashes={}
    for extension in ['pdf','svg','png']:
        path=root/('figure.'+extension); fig.savefig(path,dpi=180,facecolor='white'); hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig); report['provenance']['figure_sha256']=hashes
    (root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__': plot(Path(sys.argv[1]))
