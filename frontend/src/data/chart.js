// Reference data + demo chart, ported verbatim from frontend/public/prototype.html.
// Replace PATIENTS with GET /patients (PRD 8.3) once the backend is up — same shape.

export const ROLES = ["Hospitalist","Night Resident","Nursing","Pharmacy","PT","OT","Case Management","Cardiology","Orthopedics","Dietitian","Infectious Disease"]
export const OWNERS = ["Charge RN","Hospitalist","Case Management","Pharmacy","Social Work","PT/OT","Unit Clerk"]

export const TOPICS = {
  anticoagulation:{label:"Anticoagulation",values:["continue","hold"],sev:"high"},
  weight_bearing:{label:"Weight-bearing",values:["full","partial","non-weight-bearing"],sev:"high"},
  destination:{label:"Discharge destination",values:["home","home with home health","SNF","inpatient rehab"],sev:"high"},
  diet:{label:"Diet",values:["regular","cardiac 2g Na","carb-consistent","NPO","clear liquids"],sev:"med"},
  fluids:{label:"Fluids",values:["restrict","encourage"],sev:"med"},
  isolation:{label:"Isolation",values:["contact precautions","none"],sev:"med"},
}

export const FIELDS = [
  {key:"codeStatus",label:"Code status",sev:"high",why:"Oncoming staff cannot act safely in an emergency without it.",ph:"e.g. Full code"},
  {key:"allergies",label:"Allergies",sev:"high",why:"Allergy status is not documented in the handoff, so orders may be placed without it.",ph:"e.g. NKDA, or drug and reaction"},
  {key:"followUpOwner",label:"Post-discharge follow-up owner",sev:"med",why:"Nobody is named to see this patient after discharge, so follow-up is likely to slip.",ph:"e.g. PCP Dr. Hale"},
  {key:"medRec",label:"Medication reconciliation",sev:"med",why:"Discharge medications have not been reconciled against home medications.",ph:"e.g. Done by pharmacy"},
  {key:"familyContact",label:"Family or surrogate contact",sev:"low",why:"No one is listed to call if the patient's status changes or a plan needs consent.",ph:"e.g. Daughter, on file"},
]

export const TYPE_LABEL = {conflict:"Conflicting instructions",handoff:"Incomplete handoff",blocker:"Administrative blocker"}
export const SEV_LABEL = {high:"High priority",med:"Medium priority",low:"Low priority"}
export const DS_LABEL = {risk:"At risk",watch:"Watch",ready:"Ready"}
export const W = {high:3,med:2,low:1}

const RAW_PATIENTS = [
 {id:"p1",name:"Margaret A.",age:78,room:"412",dx:"Hip fracture, ORIF post-op day 2",dischargeInH:30,
  handoff:{codeStatus:"Full code",allergies:"Penicillin (rash)",familyContact:"Daughter, on file",followUpOwner:"",medRec:"Done by pharmacy"},
  pending:[{name:"Repeat hemoglobin",owner:"Night Resident"},{name:"Type and screen",owner:""}],
  blockers:[
    {id:"b1",label:"SNF insurance authorization",cat:"Prior authorization",waitingOn:"Payer",ageH:31,blocks:true},
    {id:"b2",label:"Ambulance transport not booked",cat:"Transport",waitingOn:"Case Management",ageH:6,blocks:true}],
  notes:[
   {role:"Orthopedics",author:"Dr. Reyes",h:40,text:"Partial weight-bearing on the operative leg for 6 weeks. Toe-touch, up to 50%.",tags:[["weight_bearing","partial"]]},
   {role:"Hospitalist",author:"Dr. Okafor",h:30,text:"Continue enoxaparin 40 mg daily for VTE prophylaxis after ORIF.",tags:[["anticoagulation","continue"]]},
   {role:"PT",author:"J. Lindqvist, PT",h:18,text:"Tolerated gait training well. Progressed to full weight-bearing as tolerated per protocol.",tags:[["weight_bearing","full"]]},
   {role:"Case Management",author:"T. Nguyen, RN",h:12,text:"Plan is SNF for rehab. Authorization submitted to the payer.",tags:[["destination","SNF"]]},
   {role:"Pharmacy",author:"S. Bhatt, PharmD",h:9,text:"Hgb 8.1, down from 9.6. Recommend holding enoxaparin until repeat Hgb is resulted.",tags:[["anticoagulation","hold"]]},
   {role:"Nursing",author:"K. Adeyemi, RN",h:4,text:"Daughter says the family expects her to come home Friday.",tags:[["destination","home"]]},
  ]},
 {id:"p2",name:"Robert C.",age:64,room:"407",dx:"Heart failure exacerbation, day 3",dischargeInH:20,
  handoff:{codeStatus:"",allergies:"NKDA",familyContact:"Wife, Linda",followUpOwner:"Cardiology clinic",medRec:"Done by pharmacy"},
  pending:[],
  blockers:[
    {id:"b1",label:"Home oxygen order not placed",cat:"Equipment (DME)",waitingOn:"Hospitalist",ageH:14,blocks:true},
    {id:"b2",label:"Diuretic teaching not completed",cat:"Patient education",waitingOn:"Nursing",ageH:20,blocks:true}],
  notes:[
   {role:"Cardiology",author:"Dr. Shah",h:34,text:"Fluid restriction 1.5 L per day. 2 g sodium diet.",tags:[["fluids","restrict"],["diet","cardiac 2g Na"]]},
   {role:"Night Resident",author:"Dr. Alvarez",h:13,text:"Patient very thirsty overnight. Encourage oral fluids and okay to liberalize the diet.",tags:[["fluids","encourage"],["diet","regular"]]},
   {role:"Dietitian",author:"M. Okoye, RD",h:8,text:"Started 2 g sodium diet education with patient and wife.",tags:[["diet","cardiac 2g Na"]]},
  ]},
 {id:"p3",name:"Priya S.",age:41,room:"305",dx:"Laparoscopic cholecystectomy, post-op day 1",dischargeInH:6,
  handoff:{codeStatus:"Full code",allergies:"NKDA",familyContact:"",followUpOwner:"Surgery clinic",medRec:"Done by pharmacy"},
  pending:[],blockers:[],
  notes:[
   {role:"Hospitalist",author:"Dr. Okafor",h:10,text:"Advance to regular diet as tolerated. Pain controlled on oral medication.",tags:[["diet","regular"]]},
  ]},
 {id:"p4",name:"James O.",age:55,room:"418",dx:"Diabetic ketoacidosis, resolved",dischargeInH:26,
  handoff:{codeStatus:"Full code",allergies:"Sulfa (hives)",familyContact:"Partner, Sam",followUpOwner:"Endocrinology",medRec:""},
  pending:[{name:"HbA1c",owner:""}],
  blockers:[
    {id:"b1",label:"Continuous glucose monitor prior authorization",cat:"Prior authorization",waitingOn:"Payer",ageH:52,blocks:true},
    {id:"b2",label:"Insulin pen teaching not completed",cat:"Patient education",waitingOn:"Nursing",ageH:10,blocks:true}],
  notes:[
   {role:"Dietitian",author:"M. Okoye, RD",h:20,text:"Carbohydrate-consistent diet. Reviewed meal timing with insulin.",tags:[["diet","carb-consistent"]]},
  ]},
 {id:"p5",name:"Elena V.",age:83,room:"421",dx:"Pneumonia, improving on day 4",dischargeInH:44,
  handoff:{codeStatus:"DNR/DNI",allergies:"",familyContact:"Son, Marcus",followUpOwner:"PCP Dr. Hale",medRec:"Done by pharmacy"},
  pending:[{name:"Sputum culture",owner:"Hospitalist"}],
  blockers:[
    {id:"b1",label:"Home health referral awaiting physician signature",cat:"Referral",waitingOn:"Hospitalist",ageH:21,blocks:true}],
  notes:[
   {role:"Infectious Disease",author:"Dr. Wen",h:30,text:"Contact precautions until MRSA screen results.",tags:[["isolation","contact precautions"]]},
   {role:"Case Management",author:"T. Nguyen, RN",h:10,text:"Plan is home with home health nursing twice weekly.",tags:[["destination","home with home health"]]},
   {role:"PT",author:"J. Lindqvist, PT",h:7,text:"Needs standby assist for transfers. Recommend SNF; not safe alone at home.",tags:[["destination","SNF"]]},
   {role:"Nursing",author:"K. Adeyemi, RN",h:5,text:"MRSA screen negative. Precautions lifted and signage removed.",tags:[["isolation","none"]]},
  ]},
 {id:"p6",name:"David L.",age:29,room:"310",dx:"Appendectomy, post-op day 1",dischargeInH:3,
  handoff:{codeStatus:"Full code",allergies:"NKDA",familyContact:"Mother, on file",followUpOwner:"Surgery clinic",medRec:"Done by pharmacy"},
  pending:[],blockers:[],
  notes:[
   {role:"Hospitalist",author:"Dr. Okafor",h:8,text:"Regular diet. Cleared for discharge this afternoon once he has voided.",tags:[["diet","regular"]]},
  ]},
]

// Oldest note first, so seq ascends with recency (prototype.html:347-349).
export const PATIENTS = RAW_PATIENTS.map((p) => ({
  ...p,
  notes: [...p.notes].sort((a, b) => b.h - a.h).map((n, i) => ({ ...n, seq: i + 1 })),
}))
