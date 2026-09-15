function results = dr_classical_baseline(splitCsv, outJson)
% DR_CLASSICAL_BASELINE  The control arm: MATLAB Image Processing Toolbox only.
%
%   results = dr_classical_baseline('../../artifacts/model/split.csv', 'baseline.json')
%
% WHY THIS EXISTS
% The problem statement asks us to prove the integrated pipeline beats "any single
% technique approach". This classical pipeline IS that single technique. It is the
% control arm of the ablation table, run on the IDENTICAL splits as the CNN, so the
% comparison is apples to apples. Presenting a deep model without a baseline is the
% single most common way a hackathon submission fails to make its own case.
%
% It also answers the awkward question. MathWorks set this problem; a team that deleted
% MATLAB entirely invites hostility. Here MATLAB is doing real, load-bearing work.
%
% THE PIPELINE (classical, no learned features except the final SVM)
%   1. Green channel + illumination flattening
%   2. Exudates      : morphological top-hat, optic disc excluded
%   3. Microaneurysms: extended-minima transform on the complemented green channel
%   4. Haemorrhages  : same dark-blob response, larger size band
%   5. Vessels       : matched filtering with a bank of oriented Gaussian kernels
%   6. Grading       : an SVM over the resulting lesion-count feature vector
%
% Toolboxes required: Image Processing, Statistics and Machine Learning.

if nargin < 1, splitCsv = fullfile('..','..','artifacts','model','split.csv'); end
if nargin < 2, outJson  = 'classical_baseline_metrics.json'; end

% readtable's header detection fails on this file: the paths are long absolute POSIX
% paths, and 'path' collides with a MATLAB builtin, so auto-detection consumed the first
% DATA row as the header (giving 3661 rows and a variable literally named after an image).
% Read it explicitly by position instead of trusting detection.
opts = detectImportOptions(splitCsv, 'Delimiter', ',', 'ReadVariableNames', false);
opts.DataLines = [2 Inf];                       % skip the real header row ourselves
opts = setvartype(opts, {'char','double','char'});
T = readtable(splitCsv, opts);
T.Properties.VariableNames = {'img_path','grade','split'};

feats = []; labels = []; splits = strings(0);

fprintf('Extracting classical features from %d images...\n', height(T));
for i = 1:height(T)
    I = imread(T.img_path{i});
    f = extract_features(I);
    feats(end+1, :) = f;            %#ok<AGROW>
    labels(end+1)   = T.grade(i);   %#ok<AGROW>
    splits(end+1)   = string(T.split{i}); %#ok<AGROW>
    if mod(i, 250) == 0, fprintf('  %d/%d\n', i, height(T)); end
end

isTrain = splits == "train";
mdl = fitcecoc(feats(isTrain, :), labels(isTrain), ...
    'Learners', templateSVM('KernelFunction', 'rbf', 'Standardize', true), ...
    'Coding', 'onevsone');

pred = predict(mdl, feats(~isTrain, :));
truth = labels(~isTrain)';

results = struct();
results.method = 'MATLAB classical CV + SVM (control arm)';
results.n_train = sum(isTrain);
results.n_val   = sum(~isTrain);
results.qwk     = quadratic_weighted_kappa(truth, pred, 5);
results.confusion = confusionmat(truth, pred, 'Order', 0:4);

refTruth = truth >= 2; refPred = pred >= 2;
tp = sum(refPred & refTruth);  tn = sum(~refPred & ~refTruth);
fp = sum(refPred & ~refTruth); fn = sum(~refPred & refTruth);
results.referable_sensitivity = tp / max(tp + fn, 1);
results.referable_specificity = tn / max(tn + fp, 1);
results.feature_names = feature_names();

fid = fopen(outJson, 'w'); fwrite(fid, jsonencode(results, 'PrettyPrint', true)); fclose(fid);
fprintf('\nCLASSICAL BASELINE  QWK %.4f  sens %.4f  spec %.4f\n  -> %s\n', ...
    results.qwk, results.referable_sensitivity, results.referable_specificity, outJson);
end

% =========================================================================
function f = extract_features(I)
I = im2double(imresize(crop_to_retina(I), [1024 1024]));
G = I(:,:,2);
mask = rgb2gray(I) > 0.04;

% illumination flattening
bg   = imopen(G, strel('disk', 40));
flat = imsubtract(G, bg);

[cx, cy, r] = find_optic_disc(G, mask);
discMask = false(size(G));
[X, Y] = meshgrid(1:size(G,2), 1:size(G,1));
discMask((X-cx).^2 + (Y-cy).^2 <= (1.4*r)^2) = true;

% --- hard exudates: bright, sharp, disc excluded
th = imtophat(G, strel('disk', 12));
th(discMask | ~mask) = 0;
exBW = imbinarize(th, max(0.05, 3*std(th(mask)))) & mask;
exBW = bwareaopen(exBW, 12);
exStats = regionprops(exBW, 'Area');

% --- dark lesions: extended-minima on the complement
Gc = imcomplement(G); Gc(~mask) = 0;
emin = imextendedmax(Gc, 0.08) & mask;
vessels = matched_filter_vessels(G, mask);
emin = emin & ~imdilate(vessels, strel('disk', 2));
darkStats = regionprops(emin, 'Area', 'Eccentricity');
areas = [darkStats.Area];
ecc   = [darkStats.Eccentricity];
maIdx = areas > 4  & areas <= 60  & ecc < 0.85;
heIdx = areas > 60 & areas <= 3000;

f = [ numel(exStats), sum([exStats.Area]), ...
      sum(maIdx), sum(heIdx), ...
      sum(vessels(:)) / max(sum(mask(:)), 1), ...
      mean(G(mask)), std(G(mask)), ...
      mean(flat(mask)), r ];
end

function names = feature_names()
names = {'n_exudates','exudate_area','n_microaneurysms','n_haemorrhages', ...
         'vessel_density','mean_green','std_green','mean_flattened','disc_radius'};
end

function V = matched_filter_vessels(G, mask)
% Chaudhuri matched filter: a bank of oriented Gaussian line kernels.
V = zeros(size(G));
for theta = 0:15:165
    k = imrotate(fspecial('gaussian', [15 15], 2) .* ...
                 repmat(linspace(-1, 1, 15), 15, 1), theta, 'bilinear', 'crop');
    V = max(V, imfilter(imcomplement(G), k, 'replicate'));
end
V(~mask) = 0;
V = imbinarize(V, graythresh(V(mask))) & mask;
V = bwareaopen(V, 30);
end

function [cx, cy, r] = find_optic_disc(G, mask)
sm = imgaussfilt(G, size(G,2)/28); sm(~mask) = 0;
[~, idx] = max(sm(:));
[cy, cx] = ind2sub(size(sm), idx);
r = size(G,2) / 14;
end

function J = crop_to_retina(I)
g = rgb2gray(I); bw = g > 10;
st = regionprops(bwareafilt(bw, 1), 'BoundingBox');
if isempty(st), J = I; return; end
J = imcrop(I, st(1).BoundingBox);
end

function k = quadratic_weighted_kappa(t, p, n)
O = confusionmat(t, p, 'Order', 0:(n-1));
w = (repmat((0:n-1)', 1, n) - repmat(0:n-1, n, 1)).^2 / (n-1)^2;
E = (sum(O,2) * sum(O,1)); E = E / sum(E(:)) * sum(O(:));
k = 1 - sum(w(:).*O(:)) / max(sum(w(:).*E(:)), eps);
end
