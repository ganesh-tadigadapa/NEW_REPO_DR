function disc_fovea_reference(listFile, outJson)
% DISC_FOVEA_REFERENCE  MATLAB optic-disc and fovea localisation reference.
%
% Reads a list of ALREADY-PREPROCESSED 1024px images (written by the Python caller so
% both implementations see identical pixels) and reports disc/fovea centres in that
% frame. scripts/eval_localisation.py scores these against IDRiD ground truth.
%
% Compared against GROUND TRUTH, never against the Python detector directly: the two use
% different algorithms (imfindcircles vs a brightness/Hough hybrid), so a detector-vs-
% detector distance would carry no information about which is right.

fid = fopen(listFile,'r'); paths = textscan(fid,'%s','Delimiter','\n'); fclose(fid);
paths = paths{1};
out = cell(numel(paths),1);
for i = 1:numel(paths)
    p = strtrim(paths{i});
    if isempty(p), continue; end
    try
        I = imread(p);
        [d, f] = locate(I);
        out{i} = struct('image', p, 'ok', true, ...
            'disc_x', d(1), 'disc_y', d(2), 'fovea_x', f(1), 'fovea_y', f(2));
    catch e
        out{i} = struct('image', p, 'ok', false, 'disc_x', NaN, 'disc_y', NaN, ...
            'fovea_x', NaN, 'fovea_y', NaN);
    end
    if mod(i,25)==0, fprintf('  %d/%d\n', i, numel(paths)); end
end
out = out(~cellfun(@isempty,out));
fid = fopen(outJson,'w'); fprintf(fid,'%s',jsonencode([out{:}],'PrettyPrint',true)); fclose(fid);
fprintf('wrote %s\n', outJson);
end

function [disc, fovea] = locate(I)
% Optic disc: the brightest compact region. Green channel is poor for the disc (it is
% bright in all channels), so use the red channel where the disc dominates most.
G = double(I(:,:,2))/255; R = double(I(:,:,1))/255;
retina = rgb2gray(I) > 10;

bright = imgaussfilt(R, 15);
bright(~retina) = 0;
[~, idx] = max(bright(:));
[dy, dx] = ind2sub(size(bright), idx);
disc = [dx, dy];

% Fovea: the darkest region about 2-3 disc diameters TEMPORAL to the disc, near the
% horizontal meridian.
%
% A pure annulus search was tried first and failed badly -- 528 px mean error against
% IDRiD ground truth, 0% within one disc radius, i.e. no better than chance. The reason
% is that an unconstrained ring contains dark vessel arcades in every direction, so the
% minimum lands anywhere. Two constraints fix it:
%   1. DIRECTION: the fovea lies temporal to the disc, which in a centred fundus frame
%      means horizontally toward the image centre, not away from it.
%   2. ELEVATION: it sits close to the horizontal meridian, within about 30 degrees.
dark = imgaussfilt(G, 25);
dark(~retina) = Inf;
[h, w] = size(dark);
[X, Y] = meshgrid(1:w, 1:h);
r = hypot(X - dx, Y - dy);
discR = w * 0.07;                     % typical disc radius at this framing

% temporal direction: from the disc toward the horizontal centre of the frame
dirSign = sign((w/2) - dx);
if dirSign == 0, dirSign = 1; end
dxs = (X - dx) * dirSign;             % positive on the temporal side

ang = abs(atan2(Y - dy, max(abs(X - dx), 1)));   % elevation off horizontal
band = r > 1.8*discR & r < 3.5*discR & dxs > 0 & ang < deg2rad(30);
if nnz(band) < 50                      % fall back to the ring if the cone is empty
    band = r > 1.8*discR & r < 3.5*discR & dxs > 0;
end
dark(~band) = Inf;
[~, idx2] = min(dark(:));
[fy, fx] = ind2sub(size(dark), idx2);
fovea = [fx, fy];
end
