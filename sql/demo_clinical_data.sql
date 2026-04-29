-- Demo clinical data for Clinical Co-Pilot development
-- Patients: Ted Shaw (pid=1), Eduardo Perez (pid=4), Farrah Rolle (pid=5), Nora Cohen (pid=8), Jim Moses (pid=17)

SET @provider_id = 1;
SET @facility_id = 3;

-- -------------------------------------------------------
-- ENCOUNTERS
-- -------------------------------------------------------
INSERT INTO form_encounter (date, reason, facility, facility_id, pid, encounter, provider_id, pos_code, class_code) VALUES
-- Ted Shaw: HTN + T2DM follow-up
('2026-03-15 09:00:00', 'Hypertension and Type 2 Diabetes follow-up', 'Your Clinic', @facility_id, 1, 1001, @provider_id, 11, 'AMB'),
-- Ted Shaw: chest pain eval
('2026-04-10 14:00:00', 'Chest pain and shortness of breath', 'Your Clinic', @facility_id, 1, 1002, @provider_id, 11, 'AMB'),
-- Eduardo Perez: COPD management
('2026-03-20 10:30:00', 'COPD exacerbation follow-up', 'Your Clinic', @facility_id, 4, 1003, @provider_id, 11, 'AMB'),
-- Farrah Rolle: prenatal visit
('2026-04-05 11:00:00', 'OB prenatal visit - 28 weeks', 'Your Clinic', @facility_id, 5, 1004, @provider_id, 11, 'AMB'),
-- Nora Cohen: anxiety and migraines
('2026-04-12 08:30:00', 'Anxiety disorder and migraine management', 'Your Clinic', @facility_id, 8, 1005, @provider_id, 11, 'AMB'),
-- Jim Moses: post-MI cardiac follow-up
('2026-04-14 09:00:00', 'Cardiac follow-up post-MI', 'Your Clinic', @facility_id, 17, 1006, @provider_id, 11, 'AMB');

-- Link encounters to forms table
INSERT INTO forms (date, encounter, form_name, form_id, pid, user, groupname, authorized, deleted, formdir) VALUES
('2026-03-15 09:00:00', 1001, 'New Patient Encounter', 1001, 1,  'admin', 'Default', 1, 0, 'newpatient'),
('2026-04-10 14:00:00', 1002, 'New Patient Encounter', 1002, 1,  'admin', 'Default', 1, 0, 'newpatient'),
('2026-03-20 10:30:00', 1003, 'New Patient Encounter', 1003, 4,  'admin', 'Default', 1, 0, 'newpatient'),
('2026-04-05 11:00:00', 1004, 'New Patient Encounter', 1004, 5,  'admin', 'Default', 1, 0, 'newpatient'),
('2026-04-12 08:30:00', 1005, 'New Patient Encounter', 1005, 8,  'admin', 'Default', 1, 0, 'newpatient'),
('2026-04-14 09:00:00', 1006, 'New Patient Encounter', 1006, 17, 'admin', 'Default', 1, 0, 'newpatient');

-- -------------------------------------------------------
-- VITALS
-- -------------------------------------------------------
INSERT INTO form_vitals (date, pid, user, groupname, authorized, activity, bps, bpd, weight, height, temperature, pulse, respiration, oxygen_saturation, BMI) VALUES
-- Ted Shaw: elevated BP, overweight
('2026-03-15 09:05:00', 1,  'admin', 'Default', 1, 1, '158', '96',  210.0, 68.0, 98.4, 78, 16, 97.0, 31.9),
('2026-04-10 14:05:00', 1,  'admin', 'Default', 1, 1, '162', '100', 212.0, 68.0, 98.6, 92, 20, 95.0, 32.2),
-- Eduardo Perez: COPD, low O2
('2026-03-20 10:35:00', 4,  'admin', 'Default', 1, 1, '130', '82',  178.0, 66.0, 98.0, 88, 22, 91.0, 28.7),
-- Farrah Rolle: pregnant, normal vitals
('2026-04-05 11:05:00', 5,  'admin', 'Default', 1, 1, '118', '74',  168.0, 64.0, 98.6, 80, 16, 99.0, 28.8),
-- Nora Cohen: slightly elevated HR (anxiety)
('2026-04-12 08:35:00', 8,  'admin', 'Default', 1, 1, '122', '78',  145.0, 65.0, 98.2, 98, 18, 99.0, 24.1),
-- Jim Moses: post-MI, low BP on meds
('2026-04-14 09:05:00', 17, 'admin', 'Default', 1, 1, '108', '68',  195.0, 70.0, 98.0, 64, 14, 97.0, 27.9);

-- -------------------------------------------------------
-- SOAP NOTES
-- -------------------------------------------------------
INSERT INTO form_soap (date, pid, activity, authorized, groupname,
  subjective, objective, assessment, plan) VALUES
-- Ted Shaw: HTN/DM follow-up
('2026-03-15 09:10:00', 1, 1, 1, 'Default',
  'Patient reports compliance with lisinopril and metformin. Occasional headaches. Denies polyuria. HbA1c last drawn 3 months ago was 8.1%.',
  'BP 158/96 mmHg. HR 78. Weight 210 lbs. BMI 31.9. No peripheral edema. Lungs clear.',
  'Uncontrolled hypertension. Type 2 diabetes mellitus suboptimally controlled. Overweight.',
  'Increase lisinopril to 20mg daily. Continue metformin 1000mg BID. Order HbA1c, CMP, lipid panel. Dietary counseling. Follow up in 6 weeks.'),
-- Ted Shaw: chest pain
('2026-04-10 14:10:00', 1, 1, 1, 'Default',
  'Patient presents with 3-day history of exertional chest tightness and mild dyspnea. No radiation. Denies diaphoresis or syncope.',
  'BP 162/100. HR 92. O2 sat 95% on room air. RRR, no murmurs. Mild bibasilar crackles.',
  'Atypical chest pain. Possible hypertensive urgency. Rule out ACS and early CHF.',
  'EKG ordered - normal sinus rhythm. Troponin x2 negative. Chest X-ray: mild cardiomegaly. Add amlodipine 5mg. Cardiology referral placed. Return if symptoms worsen.'),
-- Eduardo Perez: COPD
('2026-03-20 10:40:00', 4, 1, 1, 'Default',
  'Patient with known COPD reports increased dyspnea over past week, productive cough with yellowish sputum. Used rescue inhaler 4x/day. Former 40 pack-year smoker, quit 5 years ago.',
  'BP 130/82. HR 88. RR 22. O2 sat 91% on room air. Diffuse expiratory wheezing bilaterally. Prolonged expiratory phase.',
  'COPD exacerbation. Possible bacterial superinfection.',
  'Azithromycin 500mg x1, then 250mg x4 days. Prednisone 40mg x5 days. Continue tiotropium and albuterol. O2 at 2L/min PRN. Follow up in 5 days or sooner if worsening.'),
-- Farrah Rolle: prenatal
('2026-04-05 11:10:00', 5, 1, 1, 'Default',
  'G2P1, 28 weeks by LMP. Reports mild lower back pain and occasional Braxton-Hicks contractions. No bleeding, no leaking fluid. Fetal movement active.',
  'BP 118/74. HR 80. Weight 168 lbs (up 4 lbs since last visit). Fundal height 28 cm. FHR 148 bpm by Doppler. Mild pedal edema bilateral.',
  'Uncomplicated intrauterine pregnancy at 28 weeks. Mild dependent edema.',
  'GDM screening ordered (1-hour glucose). TDAP vaccine today. Continue prenatal vitamins. Anatomy ultrasound reviewed - normal. Return in 4 weeks.'),
-- Nora Cohen: anxiety/migraines
('2026-04-12 08:40:00', 8, 1, 1, 'Default',
  'Patient reports 3-4 migraines/month, often triggered by stress and poor sleep. Sertraline 100mg helpful for mood but still has breakthrough anxiety around work deadlines. Uses sumatriptan with partial relief.',
  'BP 122/78. HR 98 (elevated, patient reports anxiety today). Alert, oriented. No focal neurological deficits.',
  'Generalized anxiety disorder, partially controlled. Migraine, without aura, chronic.',
  'Increase sertraline to 150mg. Add propranolol 20mg BID for migraine prophylaxis and anxiety. Continue sumatriptan PRN. Refer to CBT/therapy. Sleep hygiene counseling. Follow up 8 weeks.'),
-- Jim Moses: post-MI
('2026-04-14 09:10:00', 17, 1, 1, 'Default',
  'Patient 6 months post-STEMI (LAD). On aspirin, atorvastatin, metoprolol, lisinopril. Reports fatigue with exertion (2-3 blocks). No chest pain at rest. Denies edema or orthopnea.',
  'BP 108/68. HR 64. Weight 195 lbs. JVP not elevated. RRR, S3 absent. No lower extremity edema.',
  'Ischemic cardiomyopathy post-STEMI. Stable. NYHA Class II symptoms.',
  'Echo ordered - EF 45% (stable vs last). Continue current medications. Cardiac rehab referral reinforced. Low-sodium diet counseled. Repeat BMP for K+ monitoring on ACE inhibitor. Follow up 3 months.');

-- -------------------------------------------------------
-- ACTIVE MEDICATIONS (prescriptions)
-- -------------------------------------------------------
INSERT INTO prescriptions (patient_id, provider_id, date_added, start_date, drug, dosage, route, refills, active, note, indication, txDate, ntx, rtx, usage_category_title, request_intent_title) VALUES
-- Ted Shaw
(1, @provider_id, '2026-01-10', '2026-01-10', 'Lisinopril',     '20mg',   'Oral', 11, 1, 'Take once daily in the morning', 'Hypertension',              '2026-01-10', 0, 0, '', ''),
(1, @provider_id, '2026-01-10', '2026-01-10', 'Metformin',      '1000mg', 'Oral', 11, 1, 'Take twice daily with meals',     'Type 2 Diabetes',           '2026-01-10', 0, 0, '', ''),
(1, @provider_id, '2026-04-10', '2026-04-10', 'Amlodipine',     '5mg',    'Oral', 5,  1, 'Take once daily',                 'Hypertension',              '2026-04-10', 0, 0, '', ''),
-- Eduardo Perez
(4, @provider_id, '2025-06-01', '2025-06-01', 'Tiotropium',     '18mcg',  'Inhaled', 5, 1, '1 puff once daily via HandiHaler', 'COPD',                   '2025-06-01', 0, 0, '', ''),
(4, @provider_id, '2025-06-01', '2025-06-01', 'Albuterol',      '90mcg',  'Inhaled', 5, 1, '2 puffs every 4-6 hours PRN',      'COPD / Bronchospasm',    '2025-06-01', 0, 0, '', ''),
(4, @provider_id, '2026-03-20', '2026-03-20', 'Azithromycin',   '250mg',  'Oral',    0, 1, 'Complete 5-day course',            'COPD exacerbation',       '2026-03-20', 0, 0, '', ''),
(4, @provider_id, '2026-03-20', '2026-03-20', 'Prednisone',     '40mg',   'Oral',    0, 1, 'Taper over 5 days',                'COPD exacerbation',       '2026-03-20', 0, 0, '', ''),
-- Farrah Rolle
(5, @provider_id, '2025-10-01', '2025-10-01', 'Prenatal Vitamins', '1 tablet', 'Oral', 5, 1, 'Take once daily',              'Prenatal care',            '2025-10-01', 0, 0, '', ''),
(5, @provider_id, '2025-10-01', '2025-10-01', 'Folic Acid',     '1mg',    'Oral',    5, 1, 'Take once daily',                 'Prenatal care',            '2025-10-01', 0, 0, '', ''),
-- Nora Cohen
(8, @provider_id, '2025-09-15', '2025-09-15', 'Sertraline',     '150mg',  'Oral',    5, 1, 'Take once daily in the morning',  'Generalized Anxiety Disorder', '2025-09-15', 0, 0, '', ''),
(8, @provider_id, '2026-04-12', '2026-04-12', 'Propranolol',    '20mg',   'Oral',    5, 1, 'Take twice daily',                'Migraine prophylaxis / Anxiety', '2026-04-12', 0, 0, '', ''),
(8, @provider_id, '2025-09-15', '2025-09-15', 'Sumatriptan',    '50mg',   'Oral',    3, 1, 'Take at migraine onset, may repeat x1 after 2hrs', 'Migraine', '2025-09-15', 0, 0, '', ''),
-- Jim Moses
(17, @provider_id, '2025-10-14', '2025-10-14', 'Aspirin',       '81mg',   'Oral', 11, 1, 'Take once daily with food',        'Post-MI antiplatelet',     '2025-10-14', 0, 0, '', ''),
(17, @provider_id, '2025-10-14', '2025-10-14', 'Atorvastatin',  '80mg',   'Oral', 11, 1, 'Take once daily at bedtime',       'Post-MI / Hyperlipidemia', '2025-10-14', 0, 0, '', ''),
(17, @provider_id, '2025-10-14', '2025-10-14', 'Metoprolol Succinate', '50mg', 'Oral', 11, 1, 'Take once daily',             'Post-MI / Rate control',   '2025-10-14', 0, 0, '', ''),
(17, @provider_id, '2025-10-14', '2025-10-14', 'Lisinopril',    '10mg',   'Oral', 11, 1, 'Take once daily',                  'Post-MI / CHF',            '2025-10-14', 0, 0, '', '');
