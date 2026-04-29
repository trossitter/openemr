# Clinical Co-Pilot — Target User & Use Cases

---

## The User: Dr. Sarah Chen, Primary Care Physician

**Role:** Internal medicine physician, outpatient primary care practice  
**Daily load:** 18–22 scheduled patients, 8 AM–5 PM, with a 30-minute lunch that runs 15 minutes  
**Experience:** 8 years post-residency. Competent and efficient in OpenEMR. The system is not the bottleneck — her schedule is.

### Who She Is

Dr. Chen is not looking for clinical decision support that tells her how to practice medicine. She trained for that. What she needs is a system that eliminates the tax on her attention that comes from context-switching 20 times per day between patients who each have months or years of chart history she needs to re-inhabit in under two minutes.

She has 15 minutes per appointment. By the time a patient is in the room and she's navigated to their chart, she has 60–90 seconds to orient herself before the patient expects her full attention. That window is currently spent clicking through tabs: last visit's SOAP note, current meds, last labs, any flags. She is fast at this. She is also burning cognitive bandwidth she would rather spend on the patient.

Her tolerance for AI behavior: **high on recall, zero on invention.** She will use a tool that surfaces what's already in the chart. She will abandon a tool the first time it makes something up. Hallucination is not a UX problem for her — it is a patient safety problem.

### Her Workflow on a Typical Morning

```
7:55 AM  Reviews schedule in OpenEMR. 20 patients. Flags 3 as complex.
8:00 AM  Patient 1 in room. Opens chart. 60 seconds of clicking. Visits begin.
8:15 AM  Patient 1 done. Types encounter note while patient dresses. 3 minutes.
8:18 AM  30-second gap. Next patient already waiting.
8:19 AM  Patient 2 in room. Repeat.
...
12:00 PM Lunch. Catches up on 4 messages from this morning's patients.
1:00 PM  Afternoon block. 10 more patients.
5:15 PM  Last patient done. 45 minutes of chart completion remains.
```

**The moment the Co-Pilot enters her day:** Between clicking a patient name on the schedule and the patient walking in the door. The Co-Pilot loads alongside the chart, has already assembled the relevant context, and is ready to answer a question or simply surface what matters — without her having to ask.

---

## Use Cases

### Use Case 1: Pre-Visit Briefing (Primary)

**When:** 8:18 AM. Dr. Chen finishes with Patient 1 and clicks Patient 2 on her schedule.  
**What she's doing:** Simultaneously walking to the door, reviewing the patient's name, trying to remember if this is the Ted Shaw with uncontrolled hypertension or the Ted Shaw who's been doing well.  
**What she needs:** The three things most relevant to today's visit, already surfaced. Not the full chart. Not a summary of a summary. The signal.

**The use case:**
> "Ted Shaw, 79M. Scheduled reason: routine follow-up. Last visit 6 weeks ago — BP was 162/100, you added amlodipine. He's on lisinopril 20mg, metformin 1000mg BID, amlodipine 5mg (new). Today's vitals not yet taken. Last HbA1c was 8.1% three months ago — you ordered a repeat at the last visit; result not yet in chart."

**Why an agent, not a dashboard:**  
A dashboard shows you the same fields every time. This patient's most important fact today is the unresolved HbA1c order from six weeks ago — something a dashboard would bury in a results tab. An agent can reason about *what's changed, what's pending, and what matters given today's visit reason.* That inference across multiple data sources is what makes this irreducibly conversational rather than tabular.

**Agent must:**
- Pull demographics, reason for visit, last encounter SOAP note, active meds, most recent vitals, any pending orders not yet resulted
- Complete assembly in < 3 seconds (before she reaches the exam room door)
- Present as 3–5 bullet points, not a paragraph

**Agent must not:**
- Suggest diagnoses
- Speculate about why the lab hasn't resulted
- Surface information unrelated to this visit type

---

### Use Case 2: Medication Safety Check During Prescribing

**When:** Dr. Chen decides to add a new medication mid-visit.  
**What she's doing:** Typing a new prescription into OpenEMR.  
**What she needs:** Immediate awareness of interactions with current medications, and confirmation she's not duplicating a drug already on the list under a different name.

**The use case:**
> Dr. Chen types "propranolol 20mg BID" for Nora Cohen (anxiety/migraine). The Co-Pilot surfaces: "Nora is already on sertraline 150mg. Propranolol + sertraline: no contraindication, but monitor for additive hypotension. No existing beta-blocker on her list. Sumatriptan is active — propranolol is an appropriate adjunct for migraine prophylaxis."

**Why an agent, not a dashboard:**  
Drug interaction checkers already exist in OpenEMR and show pop-up alerts. They are tuned to be so broad that physicians click through them reflexively. An agent can apply the patient's specific context — this patient's age, weight, current conditions, current medications — to produce a signal rather than a noise. The same pharmacological rule means something different for a 28-year-old vs. a 79-year-old on three antihypertensives. A rules-based alert cannot make that distinction. An agent can.

**Agent must:**
- Access the full active medication list before responding
- Distinguish contraindications from monitoring advisories
- Respond in < 2 seconds from trigger

**Agent must not:**
- Block or override the physician's prescribing decision
- Present interaction data as a recommendation to not prescribe
- Fabricate interaction data not grounded in the chart

---

### Use Case 3: Between-Visit Chart Question

**When:** 12:10 PM. Dr. Chen is eating lunch and a nurse pops in: "Jim Moses called — he's having more fatigue, wants to know if it's the metoprolol."  
**What she's doing:** Trying to reconstruct Jim's cardiac history from memory to answer a question without pulling up his chart on her phone.  
**What she needs:** A fast, accurate answer to a specific clinical question about a specific patient.

**The use case:**
> Dr. Chen opens the Co-Pilot and types: "Jim Moses — could his fatigue be metoprolol-related?"
> 
> Co-Pilot responds: "Jim Moses, 81M, post-STEMI (LAD, Oct 2025). On metoprolol succinate 50mg. At his last visit (Apr 14), he reported fatigue with exertion at 2–3 blocks — you documented NYHA Class II. His HR was 64. Metoprolol-related fatigue is plausible at this HR, though his echo showed EF 45% (stable) which could independently explain exertional symptoms. You ordered a repeat BMP at that visit; result not in chart yet."

**Why an agent, not a dashboard:**  
This question requires reasoning across multiple data points simultaneously: the medication, the dose, the patient's specific cardiac history, his last documented functional status, and the timing of symptoms relative to a recent medication adjustment. No dashboard view presents these together. A chart search returns individual records in separate tabs. The agent's value is synthesis — producing a response shaped by the specific question asked, not a generic display of chart contents.

**Agent must:**
- Answer the specific question asked, not summarize the entire chart
- Ground every claim in a specific chart entry (with source)
- Flag when relevant data is missing (e.g., pending lab)

**Agent must not:**
- Diagnose the cause of fatigue
- Recommend adjusting or stopping the medication
- Present synthesized output as equivalent to a full chart review

---

### Use Case 4: End-of-Day Chart Completion Assist

**When:** 5:20 PM. Dr. Chen has 6 encounter notes to finish.  
**What she's doing:** Reconstructing what happened in visits that ended 4 hours ago.  
**What she needs:** A fast way to recall the key clinical facts from a visit so she can write an accurate SOAP note without starting from scratch.

**The use case:**
> Dr. Chen opens Eduardo Perez's incomplete encounter. Co-Pilot surfaces: "Eduardo Perez, 69M, COPD. Today's visit reason: COPD exacerbation follow-up. Vitals: BP 130/82, O2 sat 91% on room air, RR 22, HR 88. Active meds: tiotropium, albuterol, azithromycin (started Mar 20), prednisone (started Mar 20). Last SOAP (Mar 20): exacerbation with productive cough, started antibiotics and steroids."

**Why an agent, not a dashboard:**  
The value here is not showing her the data — she can do that herself. It's pre-assembling the clinically relevant subset so she can write the note in 3 minutes instead of 7. A physician completing charts at end of day is cognitively depleted. The agent reduces the reconstruction cost. A sorted list of chart tabs does not.

**Agent must:**
- Prioritize today's vitals and the visit reason
- Include the most recent prior SOAP for continuity
- Render in a format she can directly reference while typing

**Agent must not:**
- Draft the SOAP note for her (liability and accuracy reasons)
- Suggest a plan
- Pre-populate any fields in the EHR without explicit physician action

---

## What This User Would Not Choose

**A better chart view.** OpenEMR's chart is already accessible. The problem is not that the data is hard to find — it is that finding it takes attention that should go to the patient.

**A clinical decision support dashboard.** Dr. Chen does not need a system that tells her what to do. She needs a system that reduces the cost of knowing what she already needs to know.

**A general-purpose medical chatbot.** She has no use for a tool that can answer "what is the first-line treatment for hypertension." She needs one that knows *this* patient's current BP trend, *this* patient's current medications, and why *this* patient's last amlodipine prescription was added.

**The bar is not that the agent is technically possible. The bar is that the agent is the thing Dr. Chen would actually choose — and keep using — on a day when she has 20 patients, one nurse called in sick, and a difficult family conversation at 3 PM.**

---

## Traceability to Architecture

Every capability built in Stage 5 must trace back to a use case above:

| Stage 5 Capability | Use Case |
|---|---|
| Patient context assembly API (demographics + meds + encounters + vitals) | UC1, UC3, UC4 |
| Streaming response (< 3s first token) | UC1 |
| Medication list + interaction reasoning | UC2 |
| Source-grounded responses (no hallucination) | UC2, UC3 |
| Visit-specific context filtering (not full chart dump) | UC1, UC3 |
| Chart completion context surface | UC4 |
