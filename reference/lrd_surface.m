function [load,rot,displacement,min_ts]=lrd_surface(w,l,n,ti,ts,g,mu,msf,type)

res=100; %resolution (total number of points)
load=zeros(res,res,1);
displacement=zeros(res,1);
rot=zeros(res,1);

% Des_Bearing Function Initializations
esl=0;
ndd=1;
nrd=1;
perc1=0;
perc2=0;
dl=0;
dr=0;
dd1=0;
dd2=0;


[max_ver_def_alwd,max_vec_shear_def,disp_upperbound,max_load,min_load,load_upperbound,max_ang_w,rot_upperbound,Max_force_exerted,Max_moment,overal_height]=des_reinf_bearing_bsi_test_2(w,l,n,ti,ts,g,mu,type,esl,ndd,nrd,perc1,perc2,msf,dl,dr,dd1,dd2);
rss=max_ang_w/res;  %rotation steps size
dss=disp_upperbound/res; %displacement steps size




for i=1:res
    dd1=i*dss;
    displacement(i,1)=dd1;
    disp(i*.1)
    for j=1:res
        dr=j*rss;
        rot(j,1)=dr;
        [max_ver_def_alwd,max_vec_shear_def,disp_upperbound,max_load,min_load,load_upperbound,max_ang_w,rot_upperbound,Max_force_exerted,Max_moment,overal_height]=des_reinf_bearing_bsi_test_2(w,l,n,ti,ts,g,mu,type,esl,ndd,nrd,perc1,perc2,msf,dl,dr,dd1,dd2);
        load(i,j,1)=max_load;
        
    end
    
end
surf(displacement,rot,load)
VIEW(65,10)
xlabel('Displacement (mm)')
ylabel('Rotation (Rad)')
zlabel('Maximum Load (N)')

disp('The End')



%%Reinforcing Plate Thickness Check (5.3.3.5)
yield_s=235; %(Yield Stress)The steel is considered to be st-37-0 with less than 16% of sulphur
%A1=ap*bp;
A1=(w-5)*(l-5);
%Ar=A1*(1-(max_vec_shear_def/a)); %based on 5.3.3.2
Ar=A1*(1-(disp_upperbound/w));
%min_ts=1.3*max_load*(2*ti)*2*1.4/(Ar*yield_s)
 min_ts=1.3*load_upperbound*(2*8)*2*1.4/(Ar*yield_s);%Kh is considered to be equal to 2, since all of our plates are with hole, The partial safty factor is considered to be 1.4
if  3>=min_ts%ts>=min_ts 
    disp('The thickness of steel reinforcements are standard')
    disp('The minimum standard thickness is:(in mm)')
    disp(min_ts)
else
    disp('The thickness of steel reinforcements are lesser than minimum standard')
    disp('The minimum standard thickness is:(in mm)')
    disp(min_ts)
end

