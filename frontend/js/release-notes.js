// Curated release history. These are implementation summaries, not server audit logs.
export const RELEASE_VERSION='0.1.16';
export const RELEASE_NOTES=[
 {version:'0.1.16',date:'2026-11-11',time:'03:35 UTC',title:'Visible image while editing',items:['AI edit progress uses an animated gradient on the inside selection outline only','Removed opaque progress panel covering selected image','Processing status remains as a small corner pill with timer and model']},
 {version:'0.1.15',date:'2026-11-11',time:'02:20 UTC',title:'Same-image isolated part fix',items:['Single selected reference now drives isolated-part generation as a strict same-image transform','Prevents accidental labeled sheets and unrelated vehicle substitutions for requests like only chassis, no tyres, no glass','Gallery footer and source labels clarify when same-image transform mode is active']},
 {version:'0.1.14',date:'2026-11-11',time:'02:00 UTC',title:'Clear editing and dependable references',items:['Small version label and first-open development updates window','G to grab/move selected image area; unchanged crop and AI edit workflow','Local generation and edit activity with model, timer and animated selection border','Gallery image you open becomes the active reference for dissection, avoiding old chat prompts']},
 {version:'0.1.13',date:'2026-11-11',time:'—',title:'Floating image editor',items:['Movable, resizable image preview with zoom, pan, crop and area-specific AI edit','Detachable prompt and workspace restore via UMI LAB wordmark']},
 {version:'0.1.12',date:'2026-11-10',time:'—',title:'Meta SAM validation repair',items:['Fixed dependency-free SAM test; preserved Meta Muse integration']},
 {version:'0.1.11',date:'2026-11-10',time:'—',title:'Meta Muse and segmentation',items:['Muse chat and image provider support','SAM 3.1 component segmentation workflow']},
 {version:'0.1.10',date:'2026-11-10',time:'—',title:'Deployment reliability',items:['Clean source archives and watcher recovery for failed Git pushes']},
 {version:'0.1.9',date:'2026-11-10',time:'—',title:'Vehicle dissection',items:['Annotated parts maps, system sheets and isolated component sheets']}
];
