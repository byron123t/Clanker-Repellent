"""Standalone figures for complete measured benign model studies."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def plot(directory):
    report=json.loads((directory/'report.json').read_text())
    if report.get('benign') is not True or report['stage'] not in {'development','heldout'} or report['state']!='complete':
        raise ValueError('A complete benign model study is required')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':10,
                         'pdf.fonttype':42,'svg.fonttype':'none','svg.hashsalt':'repel-benign-model-study'})
    colors={'baseline':'#6b7787','contract':'#126e62'}
    names={'glm':'GLM','deepseek':'DeepSeek'}
    fig,axes=plt.subplots(1,3,figsize=(11,4.3),gridspec_kw={'width_ratios':[1.6,1,1]})
    fig.subplots_adjust(left=.16,right=.98,top=.77,bottom=.29,wspace=.45)
    for axis in axes:
        axis.set_axisbelow(True); axis.tick_params(length=0,pad=6)
        for name,spine in axis.spines.items():
            spine.set_visible(name=='bottom'); spine.set_color('#ccd2d8'); spine.set_linewidth(.6)
    primary=axes[0]
    primary.set_xlim(-3,103); primary.set_xticks([0,25,50,75,100]); primary.grid(axis='x',color='#e3e7eb',linewidth=.55)
    rows=[r for r in report['metrics'] if r['arm']!='filter-only']
    positions=list(reversed(range(len(rows))))
    for y,row in zip(positions,rows):
        point=row['verified_rate']*100; low,high=[100*v for v in row['ci95']]
        primary.errorbar(point,y,xerr=[[max(0,point-low)],[max(0,high-point)]],fmt='o',markersize=5,
                         color=colors[row['arm']],linewidth=1.2,capsize=3)
    primary.set_yticks(positions,[names[r['model']]+' · '+('Baseline' if r['arm']=='baseline' else 'Contracts')+
                                  f"\n{r['verified']}/{r['n']} verified" for r in rows])
    primary.set_ylim(-.6,len(rows)-.4); primary.set_xlabel('Verified success (%)',labelpad=10)
    primary.set_title('A  Overall · 95% task-bootstrap CI',loc='left',pad=22)
    groups={int(g['value']):g['metrics'] for g in report['groups'] if g['dimension']=='level'}
    for axis,model,panel in zip(axes[1:],['glm','deepseek'],['B','C']):
        for arm in ['baseline','contract']:
            values=[next(r['verified_rate'] for r in groups[level] if r['model']==model and r['arm']==arm)*100 for level in [1,2,3]]
            axis.plot([1,2,3],values,color=colors[arm],linewidth=1,marker='o',markersize=4)
        axis.set_ylim(-4,104); axis.set_yticks([0,25,50,75,100]); axis.set_xticks([1,2,3])
        axis.set_xlim(.8,3.2); axis.grid(axis='y',color='#e3e7eb',linewidth=.55)
        axis.set_xlabel('Authored complexity level',labelpad=10); axis.set_title(panel+'  '+names[model]+' · descriptive',loc='left',pad=22)
    axes[1].set_ylabel('Verified success (%)',labelpad=7)
    handles=[Line2D([0],[0],color=colors[a],marker='o',linewidth=1,markersize=4,label=n)
             for a,n in [('baseline','Baseline'),('contract','Task contracts')]]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.57,.11),ncol=2,frameon=False)
    fig.suptitle(('Held-out' if report['stage']=='heldout' else 'Development')+' benign generation: acceptance is not correctness',
                 x=.03,y=.97,ha='left',fontsize=12)
    fig.text(.03,.035,f"{report['design']['tasks']} authored task units · {report['design']['replicates']} replicates · {report['counts']['completed']} candidate outcomes · equal attempt/token budgets.\n"
             'Intervals resample tasks, retaining paired arms and replicates. Complexity slices are descriptive; this is a narrow synthetic benchmark.',
             fontsize=7,color='#59626d',linespacing=1.6)
    hashes={}
    for extension in ['pdf','svg','png']:
        metadata={'CreationDate':None,'ModDate':None} if extension=='pdf' else {'Date':None} if extension=='svg' else {}
        path=directory/('figure.'+extension); fig.savefig(path,dpi=220,facecolor='white',metadata=metadata)
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig); report['provenance']['figure_sha256']=hashes
    (directory/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'figures':hashes,'matplotlib':matplotlib.__version__}))


if __name__=='__main__': plot(Path(sys.argv[1]).resolve())
