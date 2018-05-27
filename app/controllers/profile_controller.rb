class ProfileController < ApplicationController
  before_action :require_user!

  def edit
    @user = current_user
  end

  def update
    @user = current_user

    if @user.update(user_profile_attributes)
      redirect_to edit_my_profile_path, notice: "Profile updated!"
    else
      render :edit
    end
  end

  private

  def user_profile_attributes
    params.require(:user).permit(:full_name)
  end
end
