"""Export standalone scientific figures from the completed benign audit report."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(directory):
    report=json.loads((directory/'report.json').read_text())
    if report.get('benign') is not True or report.get('stage')!='audit' or report.get('state')!='complete':
        raise ValueError('A complete, explicitly benign audit report is required')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':10,'axes.labelsize':8,
                         'xtick.labelsize':7,'ytick.labelsize':8,'pdf.fonttype':42,'svg.fonttype':'none','svg.hashsalt':'repel-benign-audit-v1'})
    fig,(primary,ablation)=plt.subplots(1,2,figsize=(9,4),gridspec_kw={'width_ratios':[1,1.25]})
    fig.subplots_adjust(left=.17,right=.97,top=.78,bottom=.29,wspace=.7)
    gray,teal='#6b7787','#126e62'
    for axis in [primary,ablation]:
        axis.set_xlim(-4,104); axis.set_xticks([0,25,50,75,100]); axis.grid(axis='x',color='#e3e7eb',linewidth=.55)
        axis.set_axisbelow(True); axis.tick_params(axis='both',length=0,pad=7)
        for name,spine in axis.spines.items():
            spine.set_visible(name=='bottom'); spine.set_color('#ccd2d8'); spine.set_linewidth(.6)
    rows=report['metrics']
    for index,row in enumerate(rows):
        point=100*row['false_acceptance_rate']; lo,hi=[100*x for x in row['ci95']]; color=gray if index==0 else teal
        primary.errorbar(point,1-index,xerr=[[point-lo],[hi-point]],fmt='o',markersize=5,color=color,linewidth=1.2,capsize=3)
    primary.set_ylim(-.55,1.55); primary.set_yticks([1,0],[name+f"\n{row['false_acceptance']}/{row['faults']} faults accepted" for name,row in zip(['Baseline','Task contracts'],rows)])
    primary.set_title('A  False acceptance',loc='left',pad=23,fontweight='medium'); primary.set_xlabel('Faulty candidates accepted (%) · lower is better',labelpad=10)
    effect=report['effects'][0]
    primary.text(.5,.98,f"Reduction: {100*effect['difference']:.1f} pp\n95% CI {100*effect['ci95'][0]:.1f}–{100*effect['ci95'][1]:.1f} pp",transform=primary.transAxes,
                 ha='center',va='top',fontsize=8,color=teal,linespacing=1.6)
    names={'baseline':'Baseline','structure-fix':'Structure fix only','filter-only':'Filter only','contract':'Combined'}
    checks=report['ablations']; ys=list(reversed(range(len(checks))))
    ablation.scatter([100*r['false_acceptance']/r['faults'] for r in checks],ys,s=22,color=gray,label='Faults accepted',zorder=3)
    ablation.scatter([100*r['false_rejection']/r['controls'] for r in checks],ys,s=22,color=teal,label='Controls rejected',zorder=3)
    ablation.set_yticks(ys,[names[r['arm']] for r in checks]); ablation.set_ylim(-.6,len(checks)-.4)
    ablation.set_title('B  Mechanism check (post hoc)',loc='left',pad=23,fontweight='medium')
    ablation.set_xlabel('Error rate (%) · lower is better',labelpad=10)
    ablation.legend(loc='upper center',bbox_to_anchor=(.5,-.28),ncol=2,frameon=False,fontsize=7,handlelength=1)
    fig.suptitle('Task-aware validation on an authored benign corpus',x=.03,y=.97,ha='left',fontsize=12,fontweight='medium')
    fig.text(.03,.035,f"{report['design']['tasks']} development task clusters · {report['counts']['faults']} authored faults · {report['counts']['controls']} correct formatting controls.\n"
             'A: 95% paired task-bootstrap intervals, 10,000 draws. B: same fixed sources. No model generation or real-world error-prevalence claim.',
             fontsize=7,color='#59626d',linespacing=1.6)
    hashes={}
    for extension in ['pdf','svg','png']:
        metadata={'CreationDate':None,'ModDate':None} if extension=='pdf' else {'Date':None} if extension=='svg' else {}
        path=directory/('figure.'+extension); fig.savefig(path,dpi=220,facecolor='white',metadata=metadata)
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig)
    report['provenance']['figure_sha256']=hashes
    (directory/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'figures':hashes,'matplotlib':matplotlib.__version__}))


if __name__=='__main__': plot(Path(sys.argv[1]).resolve())
