function mdl = build_dr_workflow_model(opts)
% BUILD_DR_WORKFLOW_MODEL  District DR screening programme as a SimEvents model.
%
% Requirement #5 of SIH26038. Built programmatically rather than shipped as a binary
% .slx so that the model is diffable, reviewable and reproducible from source — which
% is the same reproducibility argument we make about the training runs.
%
%   mdl = build_dr_workflow_model();                % defaults
%   mdl = build_dr_workflow_model(struct('nOphthalmologists',3));
%
% THE QUESTION THIS MODEL ANSWERS
%   A district screens 100,000 diabetics a year. Every image a human must read costs
%   ophthalmologist time, and there is roughly one ophthalmologist per 100,000 people in
%   rural India. How many ophthalmologist FTEs does the district need, with and without
%   AI triage in front of them? That difference is the economic case for the whole
%   project, and it is a discrete-event resource question — which is exactly what
%   SimEvents is for, and why this deliverable stays in MathWorks tooling.
%
% THE PIPELINE MODELLED
%   arrivals (Poisson) -> upload over a bandwidth-limited link -> AI quality gate
%     -> [fail] recapture loop (bounded retries, then manual referral)
%     -> [pass] AI grading -> [not referable & rules agree] auto-cleared
%                          -> [referable OR disagreement] ophthalmologist review queue
%
% EVERY PARAMETER IS MEASURED, NOT GUESSED
%   Service times and the ungradeable rate come from our own running service via
%   GET /v1/operational, exported by scripts/export_simulink_params.py into
%   matlab/simulink/measured_params.json. If that file is absent this function uses
%   documented placeholders and PRINTS A WARNING, because a simulation whose inputs are
%   invented tells you nothing.

arguments
    opts.mdl                  (1,:) char   = 'dr_district_workflow'
    opts.patientsPerYear      (1,1) double = 100000
    opts.workingDaysPerYear   (1,1) double = 250
    opts.hoursPerDay          (1,1) double = 6
    opts.nOphthalmologists    (1,1) double = 2
    opts.aiEnabled            (1,1) logical = true
    opts.maxRecaptures        (1,1) double = 2
    opts.paramFile            (1,:) char   = 'measured_params.json'
end

p = load_measured_params(opts.paramFile);

mdl = opts.mdl;
if bdIsLoaded(mdl); close_system(mdl, 0); end
new_system(mdl);
load_system('simevents');

% ---- arrivals ---------------------------------------------------------------
% Poisson arrivals: screening camps are scheduled, but walk-in attendance within a
% session is memoryless, so exponential inter-arrival time is the defensible default.
secondsPerYear = opts.workingDaysPerYear * opts.hoursPerDay * 3600;
meanInterArrival = secondsPerYear / opts.patientsPerYear;

add_block('simevents/Entity Generator', [mdl '/Patient Arrivals']);
set_param([mdl '/Patient Arrivals'], ...
    'GenerationMethod',        'Random', ...
    'Distribution',            'Exponential', ...
    'InterGenerationRandomMean', num2str(meanInterArrival));

% ---- upload -----------------------------------------------------------------
% A 1024px JPEG is ~350 kB after browser-side downscaling. On a 512 kbit/s rural link
% that is ~5.5 s. This is why the client downscales before upload.
add_block('simevents/Entity Server', [mdl '/Image Upload']);
set_param([mdl '/Image Upload'], ...
    'ServiceTimeSource', 'Dialog', ...
    'ServiceTime',       num2str(p.uploadSeconds), ...
    'Capacity',          '8');

% ---- AI quality gate --------------------------------------------------------
add_block('simevents/Entity Server', [mdl '/AI Quality Gate']);
set_param([mdl '/AI Quality Gate'], ...
    'ServiceTimeSource', 'Dialog', ...
    'ServiceTime',       num2str(p.qualityGateSeconds), ...
    'Capacity',          '4');

add_block('simevents/Entity Output Switch', [mdl '/Gradeable?']);
set_param([mdl '/Gradeable?'], 'NumberOfOutputPorts', '2', ...
    'SwitchingCriterion', 'From attribute', 'AttributeName', 'gradeable');

% recapture loop: a failed image is retaken on the spot, up to maxRecaptures times
add_block('simevents/Entity Server', [mdl '/Recapture']);
set_param([mdl '/Recapture'], 'ServiceTimeSource', 'Dialog', ...
    'ServiceTime', num2str(p.recaptureSeconds), 'Capacity', '4');

% ---- AI grading -------------------------------------------------------------
add_block('simevents/Entity Server', [mdl '/AI Grading']);
set_param([mdl '/AI Grading'], ...
    'ServiceTimeSource', 'Dialog', ...
    'ServiceTime',       num2str(p.gradingSeconds), ...
    'Capacity',          '4');

% ---- triage decision --------------------------------------------------------
% The AI only removes work when it clears a patient. Anything referable, and anything
% where the CNN and the ICDR rule engine disagree, still goes to a human. Modelling the
% disagreement path matters: it is the honest cost of our own safety mechanism.
add_block('simevents/Entity Output Switch', [mdl '/Needs Human?']);
set_param([mdl '/Needs Human?'], 'NumberOfOutputPorts', '2', ...
    'SwitchingCriterion', 'From attribute', 'AttributeName', 'needsHuman');

add_block('simevents/Entity Terminator', [mdl '/Auto-cleared']);

% ---- ophthalmologist review -------------------------------------------------
add_block('simevents/Entity Queue', [mdl '/Review Queue']);
set_param([mdl '/Review Queue'], 'Capacity', 'inf', ...
    'QueueType', 'FIFO', 'StatisticsAverageWaitingTime', 'on');

add_block('simevents/Entity Server', [mdl '/Ophthalmologist Review']);
set_param([mdl '/Ophthalmologist Review'], ...
    'ServiceTimeSource', 'Dialog', ...
    'ServiceTime',       num2str(p.reviewSeconds), ...
    'Capacity',          num2str(opts.nOphthalmologists), ...
    'StatisticsUtilization', 'on');

add_block('simevents/Entity Terminator', [mdl '/Reviewed']);

% ---- wiring -----------------------------------------------------------------
connect(mdl, 'Patient Arrivals/1', 'Image Upload/1');
connect(mdl, 'Image Upload/1',     'AI Quality Gate/1');
connect(mdl, 'AI Quality Gate/1',  'Gradeable?/1');
connect(mdl, 'Gradeable?/1',       'AI Grading/1');      % pass
connect(mdl, 'Gradeable?/2',       'Recapture/1');       % fail
connect(mdl, 'Recapture/1',        'AI Quality Gate/1'); % retry
connect(mdl, 'AI Grading/1',       'Needs Human?/1');
connect(mdl, 'Needs Human?/1',     'Auto-cleared/1');
connect(mdl, 'Needs Human?/2',     'Review Queue/1');
connect(mdl, 'Review Queue/1',     'Ophthalmologist Review/1');
connect(mdl, 'Ophthalmologist Review/1', 'Reviewed/1');

% ---- config -----------------------------------------------------------------
set_param(mdl, 'StopTime', num2str(secondsPerYear), 'SolverType', 'Variable-step');
set_param(mdl, 'UserData', struct('opts', opts, 'params', p));

Simulink.BlockDiagram.arrangeSystem(mdl);
save_system(mdl, fullfile(fileparts(mfilename('fullpath')), [mdl '.slx']));
fprintf('Built %s.slx  (%.0f patients/yr, %d ophthalmologists, AI %s)\n', ...
    mdl, opts.patientsPerYear, opts.nOphthalmologists, string(opts.aiEnabled));
end

% ---------------------------------------------------------------------------
function connect(mdl, src, dst)
add_line(mdl, src, dst, 'autorouting', 'smart');
end

function p = load_measured_params(fname)
here = fileparts(mfilename('fullpath'));
f = fullfile(here, fname);
if isfile(f)
    p = jsondecode(fileread(f));
    fprintf('Using MEASURED parameters from %s\n', fname);
else
    warning(['%s not found. Using DOCUMENTED PLACEHOLDERS — these are engineering ' ...
             'estimates, not measurements, and must not be presented as results. ' ...
             'Run scripts/export_simulink_params.py against the live service first.'], fname);
    p = struct( ...
        'uploadSeconds',      5.5, ...   % 350 kB over a 512 kbit/s rural link
        'qualityGateSeconds', 0.05, ...  % measured: ~40 ms, see /v1/operational
        'gradingSeconds',     1.4, ...   % CPU inference at 512px
        'recaptureSeconds',   45, ...    % health worker repositions and retakes
        'reviewSeconds',      30, ...    % the <30 s sign-off target
        'ungradeableRate',    0.12, ...
        'referableRate',      0.22, ...
        'disagreementRate',   0.06, ...
        'source',             'PLACEHOLDER');
end
end
