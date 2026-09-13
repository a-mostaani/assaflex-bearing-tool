
%% Design Reinforced Elastomeric Bearings- Assamrof

function [max_ver_def_alwd,max_vec_shear_def,disp_upperbound,max_load,min_load,load_upperbound,max_ang_w,rot_upperbound,Max_force_exerted,Max_moment,overal_height]=des_reinf_bearing_bsi_test_2(w,l,n,ti,ts,g,mu,type,esl,ndd,nrd,perc1,perc2,msf,dl,dr,dd1,dd2)
% ad in command if needed :4
% ,total_strain_i,total_strain_o,comp_strain_i,comp_strain_o,rot_strain_i,rot_strain_o

%Definition of Input arguments
%w is the width of bearing which in standard instatlation is put along
%longitudinal direction of bridge, or along the direction which has bigger rotation (mm)

%l is the length of bearing which in standard instatlation is put along
%transverse direction of bridge (mm)

%n is the number inner elastomeric layers where n+1 is the number steel
%reinforcements

%ti is the thickness of inner elastomer layers (mm)

%ts is the thickness of internal steel reinforcements (mm)

%g is G modulus or shear modulus of elastomer (N/(mm^2))

%mu is the coefficient of firicetion which is almost equal to .3 for steel
%steel, steel-elastomer, elastomer-concrete, connections, and is almost
%equal to .4 for wood elastomer connection

%type stands for the type of bearing pad to be designed, when bearing pad
%type b is in request put type equal to 2 and when type is intended put it
%equal to 3 and for type b/c type should be 2.5

%esl is about to show if there exist External Steel Layers in bearing pad to
%attach the bearing pad to the structure 

%ndd is about to show Number of Displacement Directions ,if there exist Displacement in
%both transvers and longitudinal directions, the ndd should be equal to 2
%and otherwise equal to 1

%nrd is about to show Number of Rotation Directions ,if there exist Rotation in
%both transvers and longitudinal directions, the nrd should be equal to 2
%and otherwise equal to 1

%perc1 is about to show the percentage of displacement which occures in
%transverse direction compared with longitudinal direction perc1=.3 can be a
%good estimation for ndd=2

%perc2 is about to show the percentage of rotation which occures in
%transverse direction compared with lonitudinal direction perc2=.3 can be a
%good estimation for ndd=2

%msf is about to show Manufacturing Safty Factor, all the requirements are
%multiplied or devided by msf to ensure us of safty designs msf=.7 seem to
%be reasonable since the standard lambda=0.7 is considered to be 1 in EN
%standard

%dl is Design Load of the structure, if nothing is considered put it equal to 0 else put it
%equal to the design load in (KN)

%dr is Desing Rotation of the structure, if nothing is considered put it equal to 0 else put it
%equal to the design load in (rad)

%dd1 is Design Longitudinal Displacement of the Structure, if nothing is considered put
%it equal to 0, else put it equal to the design displacement in (mm)

%dd2 is Design Transverse Displacement of the Structure, if nothing is considered put
%it equal to 0, else put it equal to the design displacement in (mm)


if ndd==1
    perc1=0;
else
    if perc1==0
        perc1=.3;
    end
end

if nrd==1
    perc2=0;
else
    if perc2==0
        perc2=.3;
    end
end

if dl~=0
    max_load=dl;%Maximum allowed Vertical load (N)
else 
    max_load=0;
end

if dr~=0
    max_ang_w=dr; %Maximum allowed rotation along W (Rad)
else 
    max_ang_w=0; %Maximum allowed rotation along L (Rad)
end

if dd1~=0 && dd2==0
    max_vec_shear_def=dd1; %Maximum Vectorial shear deflection which is the vectroial sum of shear deflection alog L and W (mm)
    max_shear_def_w=dd1; %Maximum longitudinal shear deflection (mm)
    max_shear_def_l=0;
elseif dd1==0 && dd2==0
    max_vec_shear_def=0; %Maximum vectorial shear deflection (mm)
end

if dd2~=0 && dd1==0
    max_vec_shear_def=dd2; %Maximum vectorial shear deflection (mm)
    max_shear_def_l=dd2;
    max_shear_def_w=0;
elseif dd1~=0 && dd2~=0
    max_shear_def_w=dd1;
    max_shear_def_l=dd2;
    max_vec_shear_def=sqrt(dd1^2+dd2^2); %Maximum vectorial shear deflection (mm)
end
%Definition of output arguments:

min_load=0; %Minimum allowed Vertical load in order to prevent sliping (N)
shear_stifness=0;% How much force is needed to deflect the bearing one (mm) in shear (N/mm)
max_ver_def=0; %(mm)
max_ang_l=0;
max_hor_f=0; %Maximum Horizontal Force Exerted from the bearing on the structure


sel=2;% used first in line 157 after :"total_strain_i>total_strain_o && total_strain_i-msf*7>0"



%this is method 1 which is designed for calculating the bearings mechanical properties
%without knowing the project requirements, one allowed pairs of max_load and max_rot
%are calculated in this method

%max_shear_def_w is about to show the maximum allowed shear deflection in direction of dimensioin w which is longitudinal dierection
%and max_shear_def_l is about to show the maximum allowed shear deflection in direction of dimensioin l which is transverse dierection



%algorithm initialization
%comperehensive information is provided in part 3.2 pages 8~10 of the EN1337

a=w;% a is overal Width of Bearing (shorter dimension of rectangular shape) (mm)
b=l;% b is overal length of Bearing (mm)
ap=a-20;
bp=b-20;
A=a*b; % overal plan area (mm^2)
A1=ap*bp; %effective plan area (mm^2)
ip=2*(ap+bp);% ip is the Force free primeter of bearing
to=2.5; %is the the thickness of outer elastomer layers in mm

%Calculation of total effective elastomer thickness (Mentioned in 5.3.3.3)
if esl==1
    Tq=n*ti;
elseif to<=2.5 %Design calculations should not be applied to external layers of thickness less than 2.5mm (5.3.3 page:24)
    Tq=n*ti;
else
    Tq=n*ti+2*to; 
end


te_i=ti; %Effective thickness of internal elastomer layer in compression
te_o=1.4*to;

sti3=n*(ti^3)+2*(2.5^3); %SIGMA (ti^3)



total_strain_i=0;
total_strain_o=0;
comp_strain_i=0;
comp_strain_o=0;
shear_strain_i=0;
shear_strain_o=0;
rot_strain_i=0;
rot_strain_o=0;
Kl=1; %considering the effect of any kind of forces other than live loads
total_strain_i=Kl*(comp_strain_i+shear_strain_i+rot_strain_i);
total_strain_o=Kl*(comp_strain_o+shear_strain_o+rot_strain_o);
%total strain shall not exceed the value of 7*msf

%% 5.3.3.1
s_i=A1/(ip*te_i); %shape factor of internal elastomer layers
s_o=A1/(ip*te_o); %shape factor of outer elastomer layers



   %% 5.3.3.3 Design Strian Due to Shear force (Shear Strain)
   %shear strain shall not exceed 1.00*msf .
   disp_upperbound=msf*Tq;
   if ndd==1 && dd1==0 && dd2==0
       max_shear_def_w=1*msf*Tq;
       max_vec_shear_def= max_shear_def_w;
       max_shear_def_l=0;
   elseif ndd==2 && dd1==0 && dd2==0
       max_vec_shear_def=1*msf*Tq;
       %assuming transverse shear deflection to be perc1*longitudinal_shear_def :
       max_shear_def_w=max_vec_shear_def/(sqrt(perc1^2+1));
       max_shear_def_l=perc1* max_shear_def_w;
   elseif dd1~=0 && dd2~=0
       if max_vec_shear_def>msf
           disp('Design displacement(s) are above standard value !')
       end
   end
   %calculation of Maximum Horizontal Force Excerted to the structure:
   max_hor_f=A*g*max_vec_shear_def/Tq; %5.3.3.7 b
   min_load=max_hor_f/mu; %5.3.3.6 c  ***This part can probabely be more accurate according to formula mentioned for mu

   % Now since total strain shall not exceed 7*msf and shear strain shall not
   % exceed msf we conclude that the sum of (comp_strain+rot_strain) shall not
   % exceed msf*6

   Ar=A1*(1-(max_shear_def_w/a)-(max_shear_def_l/b)); %based on 5.3.3.2
   shear_strain_o=(max_vec_shear_def/Tq);
   shear_strain_i=(max_vec_shear_def/Tq);
   %% 5.3.3.6.b (Stability Regarding Buckling)
   if dl==0
       max_load=max([2*ap*g*s_i*Ar/(3*(n*ti+2*to)),min([6*msf*g*Ar*s_i/1.5,6*msf*g*Ar*s_o/1.5])]);
   else
       load_upperbound=max([2*ap*g*s_i*Ar/(3*(n*ti+2*to)),min([6*msf*g*Ar*s_i/1.5,6*msf*g*Ar*s_o/1.5])]);
       if dl>=load_upperbound
            disp('The Designed Load is higher than capacity of this bearing')
            return
       end
   end
   %% 5.3.3.6.a (Stability Regarding Rotation)
   %calculation of total vertical deflection
   max_ver_def=n*max_load*ti*(1/(5*g*s_i^2)+1/2000)/A1; %5.3.3.7
   min_ver_def=n*min_load*ti*(1/(5*g*s_i^2)+1/2000)/A1; %5.3.3.7
   if dr==0
      max_ang_w=3*max_ver_def/(ap+bp*perc2);
   else
      rot_upperbound=3*max_ver_def/(ap+bp*perc2);
      if dr>=rot_upperbound
          disp('The Designed Rotation would make the bearing unstable')
      end
   end
   max_ang_l=max_ang_w*perc2;
   sn=1;
while sn==1
   %% 5.3.3.2 & 5.3.3.4 (Design Strain Due to Compressive Load and Rotation)
   sn=1; %as long as total strain is bigger than the standard value the sn is equal to 1, to ensure continuing while loop
   counter=0; %counter counts for number of loops to enable us of prevention of infinite loops
   ratio=0;

   if dl==0 && dr==0 %in case that both the rotation and max_load should be calculated
%rot_strain_i=(max_ang_w*ap^2+max_ang_l*bp^2)*ti/(2*sti3);
%rot_strain_o=(max_ang_w*ap^2+max_ang_l*bp^2)*to/(2*sti3);
      comp_strain_i=1.5*max_load/(g*Ar*s_i); %5.3.3.2
      comp_strain_o=1.5*max_load/(g*Ar*s_o); %5.3.3.2
      rot_strain_i=(max_ang_w*ap^2+max_ang_l*bp^2)*ti/(2*sti3);  % Recheck the formula,in BS5400.9.1-10.6 the formula is different
      rot_strain_o=(max_ang_w*ap^2+max_ang_l*bp^2)*to/(2*sti3);
      total_strain_i=comp_strain_i+rot_strain_i+shear_strain_i;
      total_strain_o=comp_strain_o+rot_strain_o+shear_strain_o;
      
      %comparison of total strain with the standard allowed total strain (msf*7)
      if total_strain_i>msf*7 || total_strain_o>msf*7
          sn=1;
      elseif total_strain_i<=msf*7 && total_strain_o<=msf*7
          sn=0;
      end

      
      if total_strain_i>total_strain_o && total_strain_i-msf*7>0
          ratio=total_strain_i/(msf*7);    
      elseif total_strain_o>total_strain_i && total_strain_o-msf*7>0
          ratio=total_strain_o/(msf*7);
      else
          ratio=1;
      end

      max_load=max_load/ratio;
      max_ang_w=max_ang_w/ratio;
      max_ang_l=max_ang_w*perc2;
      counter=counter+1;
      if counter>100
         disp('Algorithm did not converged completely')
         disp(ratio)
         disp('loop1')
         break
      end
   elseif dl~=0 && dr==0 % in case that only rotation should be calculated and max_load is predefined (the calculations are almost the same as line 192~225)
      comp_strain_i=1.5*max_load/(g*Ar*s_i); %5.3.3.2
      comp_strain_o=1.5*max_load/(g*Ar*s_o); %5.3.3.2
      rot_strain_i=(max_ang_w*ap^2+max_ang_l*bp^2)*ti/(2*sti3);  % Recheck the formula,in BS5400.9.1-10.6 the formula is different
      rot_strain_o=(max_ang_w*ap^2+max_ang_l*bp^2)*to/(2*sti3);
      total_strain_i=comp_strain_i+rot_strain_i+(max_vec_shear_def/Tq);
      total_strain_o=comp_strain_o+rot_strain_o+(max_vec_shear_def/Tq);

      if total_strain_i>msf*7 || total_strain_o>msf*7
          sn=1;
      elseif total_strain_i<=msf*7 && total_strain_o<=msf*7
          sn=0;
      end


      if total_strain_i>total_strain_o && total_strain_i-msf*7>0
          ratio=total_strain_i/(msf*7);    
      elseif total_strain_o>total_strain_i && total_strain_o-msf*7>0
          ratio=total_strain_o/(msf*7);
      else
          ratio=1;
      end

      max_ang_w=max_ang_w/ratio;
      max_ang_l=max_ang_w*perc2;
      counter=counter+1;
      if counter>200
         disp('Algorithm did not converged completely')
         disp(ratio)
         disp('loop2')
         break
      end 
      
   elseif dl==0 && dr~=0 % in case that only max_load should be calculated and rotation is predefined (the calculations are almost the same as line 192~225)
      comp_strain_i=1.5*max_load/(g*Ar*s_i); %5.3.3.2
      comp_strain_o=1.5*max_load/(g*Ar*s_o); %5.3.3.2
      rot_strain_i=(max_ang_w*ap^2+max_ang_l*bp^2)*ti/(2*sti3);  % Recheck the formula,in BS5400.9.1-10.6 the formula is different
      rot_strain_o=(max_ang_w*ap^2+max_ang_l*bp^2)*to/(2*sti3);
      total_strain_i=comp_strain_i+rot_strain_i+(max_vec_shear_def/Tq);
      total_strain_o=comp_strain_o+rot_strain_o+(max_vec_shear_def/Tq);

      if total_strain_i>msf*7 %|| abs(total_strain_o-msf*7)>.0001
          sn=1;
      elseif total_strain_i<msf*7 || abs(total_strain_i-msf*7)<.0001 %&& abs(total_strain_o-msf*7)<.0001
          sn=0;
      end


      if total_strain_i>total_strain_o && total_strain_i-msf*7>0
          ratio=total_strain_i/(msf*7);    
      elseif total_strain_o>total_strain_i && total_strain_o-msf*7>0
          ratio=total_strain_o/(msf*7);
      else
          ratio=1;
      end

      max_load=max_load/ratio;
      counter=counter+1;
      if counter>100
         disp('Algorithm did not converged completely')
         disp(ratio)
         disp('loop3')
         break
      end
      
   elseif dl~=0 && dr~=0 % in case that BOTH load and rotation are designed and we should only check them       
      comp_strain_i=1.5*max_load/(g*Ar*s_i); %5.3.3.2
      comp_strain_o=1.5*max_load/(g*Ar*s_o); %5.3.3.2
      rot_strain_i=(max_ang_w*ap^2+max_ang_l*bp^2)*ti/(2*sti3);  % Recheck the formula,in BS5400.9.1-10.6 the formula is different
      rot_strain_o=(max_ang_w*ap^2+max_ang_l*bp^2)*to/(2*sti3);
      total_strain_i=comp_strain_i+rot_strain_i+(max_vec_shear_def/Tq);
      total_strain_o=comp_strain_o+rot_strain_o+(max_vec_shear_def/Tq);
      if total_strain_o>msf*7 || total_strain_i>msf*7
          disp('The total strain due to combination of Max Load, Max Displacement and Max Rotation is above standard')
          disp(total_strain_o)
          disp(total_strain_i)
          disp('loop4')
          sn=0;
      else
          disp('The bearing is well choosen and the capable to withstand total shear strain in request.')
          total_strain_i
          
          
          
          %continueing remained calculations:
          max_ver_def_alwd=n*max_load*ti*(1/(5*g*s_i^2)+1/2000)/A1;
          %if dr==0
          %   max_ang_w=3*max_ver_def_alwd/(ap+bp*perc2);
          %else
          %    max_ang_w=dr;
          %end

         load_upperbound=min([2*ap*g*s_i*Ar/(3*(n*ti+2*to)),7*msf*(g*Ar*s_i)/1.5,7*msf*(g*Ar*s_o)/1.5]);
         rot_upperbound=min([3*max_ver_def_alwd/(ap+bp*perc2),7*msf*(2*sti3)/ti*ap^2,7*msf*(2*sti3)/to*ap^2]);



         %%Reinforcing Plate Thickness Check (5.3.3.5)
         yield_s=235; %(Yield Stress)The steel is considered to be st-37-0 with less than 16% of sulphur
         min_ts=1.3*max_load*(2*ti)*2/(Ar*yield_s);%Kh is considered to be equal to 2, since all of our plates are with hole, The partial safty factor is considered to be 1.4
         if ts>=min_ts
             disp('The thickness of steel reinforcements are standard')
             disp('The minimum standard thickness is:(in mm)')
             disp(min_ts)
         else
             disp('The thickness of steel reinforcements are lesser than minimum standard')
             disp('The minimum standard thickness is:(in mm)')
             disp(min_ts)
         end

         %Max Force Exerted to the structure:
         Rxy=A*g*max_vec_shear_def/(ti*n);
         Max_force_exerted=Rxy;
         %Max rotational resisting moment exerted on the structure
         Ks=78.4 %For a/b
         M=max_ang_w*bp^5*ap/(n*ti^3*Ks);  %assuming the width of bearing to be aligned with the longitudinal direction of bridge
         Max_moment=M;
         disp('Consider alloctation of true Ks coefficient in programm body')
          
         if type==2
            overal_height=n*ti+(n+1)*ts+2*2.5;
         elseif type==3
            disp('Make sure that the bearing plates thicknesses are choosed correctly ')
            overal_height=n*ti+(n-1)*ts+2*20;
         elseif type==2.5
            disp('Make sure that the bearing plate thickness is choosed correctly ')
            overal_height=n*ti+(n1)*ts+20+3;
         else
             error('type should be one of the following values :(2 for type B, 3 for type C, and 2.5 for type B/C)')
         end
          return
      end
       
       
   end
end

max_ver_def_alwd=n*max_load*ti*(1/(5*g*s_i^2)+1/2000)/A1;
%if dr==0
%   max_ang_w=3*max_ver_def_alwd/(ap+bp*perc2);
%else
%    max_ang_w=dr;
%end

%%Reinforcing Plate Thickness Check (5.3.3.5)
yield_s=235; %(Yield Stress)The steel is considered to be st-37-0 with less than 16% of sulphur
min_ts=1.3*max_load*(2*ti)*2*1.4/(Ar*yield_s);%Kh is considered to be equal to 2, since all of our plates are with hole, The partial safty factor is considered to be 1.4





load_upperbound=min([2*ap*g*s_i*Ar/(3*(n*ti+2*to)),7*msf*(g*Ar*s_i)/1.5,7*msf*(g*Ar*s_o)/1.5]);
rot_upperbound=min([3*max_ver_def_alwd/(ap+bp*perc2),7*msf*(2*sti3)/ti*ap^2,7*msf*(2*sti3)/to*ap^2]);



%%Reinforcing Plate Thickness Check (5.3.3.5)
yield_s=235; %(Yield Stress)The steel is considered to be st-37-0 with less than 16% of sulphur
min_ts=1.3*max_load*(2*ti)*2/(Ar*yield_s);%Kh is considered to be equal to 2, since all of our plates are with hole, The partial safty factor is considered to be 1.4
if ts>=min_ts
    disp('The thickness of steel reinforcements are standard')
    disp('The minimum standard thickness is:(in mm)')
    disp(min_ts)
else
    disp('The thickness of steel reinforcements are lesser than minimum standard')
    disp('The minimum standard thickness is:(in mm)')
    disp(min_ts)
end

%Max Force Exerted to the structure:
Rxy=A*g*max_vec_shear_def/(ti*n);
Max_force_exerted=Rxy;
%Max rotational resisting moment exerted on the structure
Ks=78.4 %For a/b
M=max_ang_w*bp^5*ap/(n*ti^3*Ks);  %assuming the width of bearing to be aligned with the longitudinal direction of bridge
Max_moment=M;
disp('Consider alloctation of true Ks coefficient in programm body')

if type==2
    overal_height=n*ti+(n+1)*ts+2*2.5;
elseif type==3
    disp('Make sure that the bearing plates thicknesses are choosed correctly ')
    overal_height=n*ti+(n-1)*ts+2*20;
elseif type==2.5
    disp('Make sure that the bearing plate thickness is choosed correctly ')
    overal_height=n*ti+(n1)*ts+20+3;
else
end



%% To Be Developed


%1-Calculation of mechanical properties having designed shear deflection

%2-Calculation of most cost-efficient bearing pad (least size, best g
%modulus,) when you have a one or all of 3 main parameters of load,
%displacement and rotation

%% Questions:

% in page 24 of the standard we have : Design calculation shall not be applied to the external top and bottom layer when their thickness is less or
% equal to 2,5 mm so it seems that we don't need to do calculations for
% external layers


% as is mentioned in BSEN, bearings are designed for ULS conditiones so how
% can we know the Service Limit State loadability of a bearing









