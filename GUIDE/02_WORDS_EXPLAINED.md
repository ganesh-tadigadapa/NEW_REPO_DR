# Every word explained

If a judge uses one of these and you blank, this is the page.

---

## Medical words

| Word | Plain meaning |
|---|---|
| **Fundus** | The back inside surface of the eye. A "fundus photo" is a photo of it. |
| **Diabetic retinopathy (DR)** | Damage to the blood vessels at the back of the eye, caused by diabetes. |
| **ICDR scale** | The official international 0–4 severity scale doctors use. |
| **Grade 0** | No damage. |
| **Grade 1 (Mild)** | Only microaneurysms — the earliest, smallest damage. |
| **Grade 2 (Moderate)** | More than just microaneurysms. **This is where referral starts.** |
| **Grade 3 (Severe)** | A lot of damage, following the "4-2-1 rule" (below). |
| **Grade 4 (Proliferative)** | Worst. New abnormal blood vessels growing. |
| **Referable DR** | Grade 2 or worse — must see an eye doctor. |
| **Microaneurysm (MA)** | A tiny bulge in a blood vessel. Looks like a small dark dot. The earliest sign. |
| **Haemorrhage** | A bleed. Bigger dark blot. |
| **Exudate** | Leaked fat/protein deposit. Bright yellow-white spot. |
| **Optic disc** | The bright circle where the nerve leaves the eye. A landmark. |
| **Fovea** | The small dark spot at the centre of vision. A landmark. |
| **4-2-1 rule** | Official test for Grade 3: lots of bleeds in **4** quadrants, OR beading in **2**, OR abnormal vessels in **1**. |
| **Neovascularisation** | New abnormal vessels growing — the sign of Grade 4. **We do not detect this.** |
| **Ungradeable** | The photo is too poor to judge. Must be retaken. |

## Computer / AI words

| Word | Plain meaning |
|---|---|
| **Model** | The AI. A big pile of numbers that learned patterns from examples. |
| **Training** | Showing the AI thousands of labelled photos until it learns. Ours took 73 minutes on a rented GPU. |
| **GPU** | A powerful chip good at AI maths. We used a free one on Kaggle. |
| **Dataset** | A collection of photos. Ours: APTOS (3,662 photos), IDRiD, DRIVE. |
| **Training set** | The photos the AI learned from (3,112 of them). |
| **Validation set** | Photos held back to check it (550). **The AI never saw these while learning.** |
| **Holdout / external test** | Photos from a *completely different source* (IDRiD). The hardest, fairest test. |
| **EfficientNetV2-S** | The brand/design of AI we used. Like "a Toyota Corolla" — a specific well-known model. |
| **CORAL / ordinal head** | Our design choice. Instead of asking "which of 5 boxes?", it asks 4 yes/no questions: worse than 0? worse than 1? worse than 2? worse than 3? Because grades are *ordered*, this is smarter — and "needs a doctor?" becomes one direct answer we can tune. |
| **Grad-CAM** | The heat-map. Shows which pixels pushed the AI's decision. |
| **Calibration** | Making the AI's confidence honest. If it says "80% sure" it should be right 80% of the time. |
| **Quality gate** | Our photo-checker at the front door. |
| **API / backend** | The engine running behind the scenes. No visuals. |
| **Frontend** | The website you actually see and click. |
| **Deploy** | Put it on the internet so anyone with the link can use it. |
| **Test suite** | 45 automatic checks that run in 30 seconds and prove nothing broke. |

## Score words — the important ones

| Word | Plain meaning | Ours |
|---|---|---|
| **Sensitivity** | Of the people who ARE sick, what % did we catch? **Missing sick people is the dangerous error.** | 0.92 internal / **0.86 external** |
| **Specificity** | Of the people who are HEALTHY, what % did we correctly leave alone? Too low = wasted appointments. | 0.93 / **0.90** |
| **QWK** | How well we agree with expert doctors, 0 = random, 1 = perfect. Being wrong by 1 grade is penalised gently; by 4 grades, harshly. | 0.92 / **0.69** |
| **Confusion matrix** | A grid: what the truth was vs what we said. The diagonal is correct answers. |  |
| **Precision** | When we say "sick", how often are we right? |  |
| **F1** | One number combining precision and sensitivity. |  |
| **False accept** | We said a bad photo was fine. **Dangerous.** |  |
| **False reject** | We refused a good photo. Annoying — patient retakes it. | 21% of photos |
| **Confidence interval (CI)** | The honest wobble range. "0.86 (0.77–0.94)" means the true value is very likely in that range. Small sample = wide range. |  |
| **Dice score** | How well two shapes overlap, 0–1. We use it for blood-vessel tracing. | 0.60 |

## Words about our process

| Word | Plain meaning |
|---|---|
| **Synthetic** | Fake, computer-generated. Our first model was trained on fake images just to test the plumbing. It is gone now. |
| **Frozen model** | Locked. We do not touch it any more, so our test results stay honest. |
| **Ablation** | Turning parts off to prove each part earns its place. |
| **Control arm / baseline** | The old-fashioned non-AI version, built so we can prove the AI is better. |
| **Ground truth** | The correct answer, as decided by a human expert. |
| **Domain shift** | The AI does worse on photos from a different hospital/camera than it trained on. **This happened to us** and we report it. |
